# HSConfig Autonomous Source Builder Lite And Strongness Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig turn deck input plus researched evidence into strong structured `source_documents.json`, then prove the existing `research-deck -> prepare -> operator_summary -> apply gate` path across the 11-deck matrix.

**Architecture:** Keep HSConfig lean: no replay parsing, no winrate analysis, no HSTuner logic, and no normal-path `Presume.json` or `Concede.json`. Add a deterministic source-document drafting layer in front of the existing `source_document_builder`, `research-deck`, and `prepare` flow; it consumes short evidence rows gathered by Codex/research, resolves card mentions to exact deck CardIDs, emits structured `source_documents.json`, and reports the first missing per-card link that prevents `SOURCE_BACKED_STRONG`.

**Tech Stack:** Python 3.11+, existing project modules, standard-library JSON/date/path tooling, pytest. No new package dependency in this wave.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Keep HSConfig scoped to pre-game HearthRanger VisionAI CustomConfig generation.
- Do not add replay, HDT, Power.log, HSReplay, winrate, post-game tuning, or candidate-promotion logic.
- Do not emit normal-path `Presume.json` or `Concede.json`.
- Runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for exact source-backed sequences.
- `reports/operator_summary.json` remains the single operator gate.
- `hsconfig apply` remains fail-closed unless the apply gate allows the package or the caller explicitly uses `--allow-source-informed`.
- Source generation may be aggressive at the evidence/claim layer, but runtime lowering must still pass `claim_can_lower_to_runtime()`.
- Long guide prose must not be stored in generated runtime files or committed fixtures; store short evidence text and source locators only.
- Tests must not call the network.
- Do not commit raw local runtime output under `outputs/`, `tmp/`, HearthRanger runtime folders, or private game evidence.

---

## Current Repo Truth This Plan Depends On

- `src/hsconfig/source_document_builder.py` already validates strict `source_documents.json`.
- `src/hsconfig/source_document_model.py` already defines supported claim kinds and `claim_can_lower_to_runtime()`.
- `src/hsconfig/guide_source_builder.py` already normalizes source documents into guide sources.
- `src/hsconfig/cli.py` already exposes `research-deck`, `prepare`, `validate`, and `apply`.
- `src/hsconfig/apply_gate.py` already enforces `operator_summary.json` before runtime apply.
- `src/hsconfig/source_claim_gap_report.py` already reports per-card missing links, but selection is still too mechanical for source-building work.
- `docs/operator/archetype-fixture-matrix.json` already lists the 11-deck matrix.
- `tests/fixtures/source_documents_*_strong.json` already exists for the matrix and should be reused for regression.

---

## File Structure

Create or modify only these areas:

- Create `src/hsconfig/source_research_manifest.py`: builds deterministic source-research instructions and deck aliases for Codex/research workers.
- Create `src/hsconfig/source_document_drafter.py`: converts short evidence rows into strict source documents.
- Modify `src/hsconfig/cli.py`: add `source-manifest` and `draft-source-documents` commands; add optional `--source-evidence-json` to `research-deck`.
- Modify `src/hsconfig/source_claim_gap_report.py`: add priority scoring and a source-builder next-action chain.
- Create `src/hsconfig/matrix_closure.py`: summarizes 11-deck fixture readiness without writing runtime.
- Add tests under `tests/` for each new public interface.
- Add `docs/operator/source-builder-workflow.md`: operator-facing short workflow.
- Update `.agents/skills/hsconfig/SKILL.md` and installed skill sync through `scripts/sync_installed_skill.py`.

Do not restructure unrelated modules.

---

### Task 1: Source Research Manifest

**Files:**
- Create: `src/hsconfig/source_research_manifest.py`
- Test: `tests/test_source_research_manifest.py`
- Read: `docs/operator/archetype-fixture-matrix.json`

**Interfaces:**
- Consumes: deck name, deck identity dictionary, candidate archetype dictionary, optional fixture matrix row.
- Produces: `build_source_research_manifest(...) -> dict[str, Any]`.

- [ ] **Step 1: Write failing manifest tests**

Add `tests/test_source_research_manifest.py`:

```python
from hsconfig.source_research_manifest import build_source_research_manifest


def test_manifest_emits_aliases_and_required_source_families():
    manifest = build_source_research_manifest(
        deck_name="MechPala",
        deck_identity={
            "deck_name": "MechPala",
            "deck_code_hash": "sha256:abc",
            "cards": [{"card_id": "BOT_001", "name": "Mech Example", "count": 2}],
        },
        candidate_archetypes={
            "primary_archetype": "mech_board_scaling",
            "candidates": [{"archetype": "mech_board_scaling", "confidence": "source_backed"}],
        },
        fixture_row={
            "deck_name": "MechPala",
            "archetype_bucket": "mech_board_scaling",
            "primary_mechanics": ["mech", "magnetic", "board_scaling"],
        },
    )

    assert manifest["deck_name"] == "MechPala"
    assert "Mech Paladin" in manifest["search_aliases"]
    assert manifest["required_source_families"] == [
        "guide",
        "mulligan_guide",
        "card_text",
        "metadata",
    ]
    assert manifest["research_questions"][0]["claim_kind"] == "card_role"
    assert manifest["card_targets"][0] == {
        "card_id": "BOT_001",
        "name": "Mech Example",
        "required_claims": ["card_role", "mechanic_usage"],
    }


def test_manifest_uses_repo_deck_name_when_no_known_alias_exists():
    manifest = build_source_research_manifest(
        deck_name="UnknownDeck",
        deck_identity={"deck_name": "UnknownDeck", "deck_code_hash": "sha256:x", "cards": []},
        candidate_archetypes={"primary_archetype": "generic_low_confidence", "candidates": []},
        fixture_row=None,
    )

    assert manifest["search_aliases"] == ["UnknownDeck"]
    assert manifest["mechanic_focus"] == ["generic_low_confidence"]
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m pytest tests/test_source_research_manifest.py -q
```

Expected: fail because `hsconfig.source_research_manifest` does not exist.

- [ ] **Step 3: Implement manifest builder**

Create `src/hsconfig/source_research_manifest.py`:

```python
from __future__ import annotations

from typing import Any


DECK_ALIASES = {
    "CtAPaladin": ["CtAPaladin", "Call to Arms Paladin", "CTA Paladin"],
    "Discolock": ["Discolock", "Discard Warlock", "Discardlock"],
    "MechPala": ["MechPala", "Mech Paladin"],
    "PirateDH": ["PirateDH", "Pirate Demon Hunter"],
    "Kingslayer": ["Kingslayer", "Kingsbane Rogue"],
}

MECHANIC_REQUIRED_CLAIMS = {
    "aggro": ["card_role", "targeting_rule"],
    "burn": ["card_role", "targeting_rule"],
    "shadow_hero_power": ["hero_power_transform", "mechanic_usage"],
    "recruit": ["card_role", "mechanic_usage"],
    "deathrattle": ["card_role", "mechanic_usage"],
    "discard": ["card_role", "mechanic_usage"],
    "mech": ["card_role", "mechanic_usage"],
    "magnetic": ["card_role", "mechanic_usage"],
    "weapon_pressure": ["card_role", "targeting_rule"],
    "weapon": ["card_role", "targeting_rule"],
    "combo": ["card_role", "combo_sequence"],
    "hero_attack": ["card_role", "targeting_rule"],
}


def build_source_research_manifest(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    candidate_archetypes: dict[str, Any],
    fixture_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mechanics = _mechanic_focus(candidate_archetypes, fixture_row)
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "search_aliases": DECK_ALIASES.get(deck_name, [deck_name]),
        "primary_archetype": str(candidate_archetypes.get("primary_archetype", "")),
        "mechanic_focus": mechanics,
        "required_source_families": ["guide", "mulligan_guide", "card_text", "metadata"],
        "research_questions": _research_questions(mechanics),
        "card_targets": _card_targets(deck_identity, mechanics),
    }


def _mechanic_focus(
    candidate_archetypes: dict[str, Any],
    fixture_row: dict[str, Any] | None,
) -> list[str]:
    if fixture_row and isinstance(fixture_row.get("primary_mechanics"), list):
        return [str(item) for item in fixture_row["primary_mechanics"]]
    primary = str(candidate_archetypes.get("primary_archetype", "")).strip()
    return [primary or "generic_low_confidence"]


def _research_questions(mechanics: list[str]) -> list[dict[str, str]]:
    questions = [
        {
            "claim_kind": "card_role",
            "question": "Which deck cards are core plan cards, payoffs, enablers, or flex cards?",
        },
        {
            "claim_kind": "mulligan_keep",
            "question": "Which exact cards are kept or thrown in mulligan and under which condition?",
        },
        {
            "claim_kind": "gameplan_posture",
            "question": "What pre-game board-value posture should GlobalValues express?",
        },
    ]
    if {"weapon", "weapon_pressure", "hero_attack"} & set(mechanics):
        questions.append(
            {
                "claim_kind": "targeting_rule",
                "question": "Which cards or attacks should prefer enemy hero versus board targets?",
            }
        )
    if "combo" in mechanics:
        questions.append(
            {
                "claim_kind": "combo_sequence",
                "question": "Which exact card order is source-backed enough for Combo.json?",
            }
        )
    return questions


def _card_targets(deck_identity: dict[str, Any], mechanics: list[str]) -> list[dict[str, Any]]:
    required = sorted({claim for mechanic in mechanics for claim in MECHANIC_REQUIRED_CLAIMS.get(mechanic, ["card_role"])})
    if not required:
        required = ["card_role"]
    return [
        {
            "card_id": str(card.get("card_id", "")),
            "name": str(card.get("name", card.get("card_id", ""))),
            "required_claims": required,
        }
        for card in deck_identity.get("cards", [])
        if isinstance(card, dict) and str(card.get("card_id", "")).strip()
    ]
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_source_research_manifest.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_research_manifest.py tests/test_source_research_manifest.py
git commit -m "Add source research manifest"
```

---

### Task 2: Evidence Row To Source Documents Drafter

**Files:**
- Create: `src/hsconfig/source_document_drafter.py`
- Test: `tests/test_source_document_drafter.py`
- Uses: `src/hsconfig/source_document_builder.py`

**Interfaces:**
- Consumes: deck identity, evidence rows, current date.
- Produces: `draft_source_documents(...) -> dict[str, Any]` with `source_documents`, `unresolved_mentions`, `draft_summary`.

- [ ] **Step 1: Write failing drafter tests**

Add `tests/test_source_document_drafter.py`:

```python
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_drafter import draft_source_documents


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "cards": [
        {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "count": 1},
        {"card_id": "SW_446", "name": "Mind Spike Enabler", "count": 2},
    ],
}


def test_drafter_resolves_card_mentions_to_strict_source_documents():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "archetype": "aggro_burn_hero_power_transform",
                "claim_kind": "hero_power_transform",
                "card_mentions": ["Darkbishop Benedictus"],
                "stance": "enable_transformed_hero_power",
                "evidence_text_short": "The deck wants the Shadow hero power online.",
                "source_confidence": "high",
            }
        ],
        current_date="2026-07-07",
    )

    documents = draft["source_documents"]
    assert documents[0]["claims"][0]["cards"] == ["BAR_735"]
    assert documents[0]["claims"][0]["claim_kind"] == "hero_power_transform"
    assert draft["draft_summary"]["resolved_claims"] == 1
    assert draft["unresolved_mentions"] == []

    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata={"cards": DECK_IDENTITY["cards"]},
        source_documents=documents,
        current_date="2026-07-07",
    )
    assert bundle["unsupported_claims"] == []


def test_drafter_reports_unresolved_mentions_without_dropping_source_context():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "claim_kind": "card_role",
                "card_mentions": ["Missing Card"],
                "stance": "core_card",
                "evidence_text_short": "Missing Card is important.",
                "source_confidence": "medium",
            }
        ],
        current_date="2026-07-07",
    )

    assert draft["source_documents"][0]["claims"] == []
    assert draft["unresolved_mentions"][0]["mention"] == "Missing Card"
    assert draft["draft_summary"]["unresolved_mentions"] == 1
```

- [ ] **Step 2: Run failing tests**

Run:

```powershell
python -m pytest tests/test_source_document_drafter.py -q
```

Expected: fail because module is missing.

- [ ] **Step 3: Implement source document drafter**

Create `src/hsconfig/source_document_drafter.py`:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any


def draft_source_documents(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    evidence_rows: list[dict[str, Any]],
    current_date: Any = None,
) -> dict[str, Any]:
    name_map = _card_name_map(deck_identity)
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    unresolved_mentions: list[dict[str, Any]] = []
    resolved_claims = 0

    for index, row in enumerate(evidence_rows, start=1):
        key = (
            str(row.get("source_url", "")),
            str(row.get("source_title", "")),
            str(row.get("source_family", "guide")),
            str(row.get("retrieved_at", "")),
        )
        document = grouped.setdefault(
            key,
            {
                "source_url": key[0],
                "source_title": key[1],
                "source_family": key[2],
                "retrieved_at": key[3],
                "deck_name": str(row.get("deck_name", deck_name)),
                "archetype": str(row.get("archetype", "")),
                "claims": [],
            },
        )
        cards, unresolved = _resolve_mentions(row, name_map)
        unresolved_mentions.extend(
            {
                "row_index": index,
                "mention": mention,
                "source_url": key[0],
                "claim_kind": str(row.get("claim_kind", "")),
            }
            for mention in unresolved
        )
        if not cards and str(row.get("scope", "card")) not in {"deck", "archetype"}:
            continue
        claim = _claim_from_row(row, cards)
        document["claims"].append(claim)
        resolved_claims += 1

    documents = list(grouped.values())
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "source_documents": documents,
        "unresolved_mentions": unresolved_mentions,
        "draft_summary": {
            "source_count": len(documents),
            "evidence_rows": len(evidence_rows),
            "resolved_claims": resolved_claims,
            "unresolved_mentions": len(unresolved_mentions),
        },
    }


def _card_name_map(deck_identity: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for card in deck_identity.get("cards", []):
        if not isinstance(card, dict):
            continue
        card_id = str(card.get("card_id", "")).strip()
        name = str(card.get("name", "")).strip()
        if card_id:
            mapping[card_id.lower()] = card_id
        if name and card_id:
            mapping[name.lower()] = card_id
    return mapping


def _resolve_mentions(
    row: dict[str, Any],
    name_map: dict[str, str],
) -> tuple[list[str], list[str]]:
    raw_cards = row.get("cards", [])
    raw_mentions = row.get("card_mentions", [])
    candidates = [*(_as_list(raw_cards)), *(_as_list(raw_mentions))]
    cards: list[str] = []
    unresolved: list[str] = []
    for candidate in candidates:
        text = str(candidate).strip()
        if not text:
            continue
        resolved = name_map.get(text.lower())
        if resolved is None:
            unresolved.append(text)
            continue
        if resolved not in cards:
            cards.append(resolved)
    return cards, unresolved


def _claim_from_row(row: dict[str, Any], cards: list[str]) -> dict[str, Any]:
    claim = {
        "claim_kind": str(row.get("claim_kind", "")),
        "cards": cards,
        "scope": str(row.get("scope", "card")),
        "stance": str(row.get("stance", "")),
        "evidence_text_short": str(row.get("evidence_text_short", row.get("reason", ""))),
        "source_confidence": str(row.get("source_confidence", "medium")),
    }
    for key in (
        "claim_confidence",
        "condition",
        "conditions",
        "selector",
        "selector_kind",
        "runtime_block",
        "runtime_value",
        "mechanic",
        "sequence",
        "timing_kind",
        "operator",
        "values",
        "option_card_id",
        "choice_card_id",
    ):
        if key in row:
            claim[key] = row[key]
    return claim


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
```

- [ ] **Step 4: Run drafter tests**

Run:

```powershell
python -m pytest tests/test_source_document_drafter.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_document_drafter.py tests/test_source_document_drafter.py
git commit -m "Add source document drafter"
```

---

### Task 3: Draft Source Documents CLI

**Files:**
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_draft_source_documents_cli.py`

**Interfaces:**
- Adds command: `hsconfig draft-source-documents --deck-name ... --deck-code ... --source-evidence-json ... --out ... --json`.
- Produces files: `source_documents.json`, `source_document_draft_report.json`.

- [ ] **Step 1: Write failing CLI tests**

Add `tests/test_draft_source_documents_cli.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import write_json


def test_draft_source_documents_cli_writes_strict_source_documents(tmp_path: Path, capsys):
    evidence_path = tmp_path / "evidence.json"
    out = tmp_path / "draft"
    cards_path = tmp_path / "cards.json"
    write_json(cards_path, {"cards": [{"card_id": "CARD_001", "dbf_id": 1, "name": "Test Card", "count": 2}]})
    write_json(
        evidence_path,
        {
            "evidence_rows": [
                {
                    "source_url": "https://example.invalid/deck",
                    "source_title": "Deck Guide",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-07T12:00:00Z",
                    "claim_kind": "card_role",
                    "card_mentions": ["Test Card"],
                    "stance": "core_card",
                    "evidence_text_short": "Test Card is core.",
                    "source_confidence": "high",
                }
            ]
        },
    )

    code = main(
        [
            "draft-source-documents",
            "--deck-name",
            "TestDeck",
            "--deck-code",
            "fixture",
            "--cards-json",
            str(cards_path),
            "--source-evidence-json",
            str(evidence_path),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "OK"
    assert (out / "source_documents.json").exists()
    documents = json.loads((out / "source_documents.json").read_text(encoding="utf-8"))
    assert documents["source_documents"][0]["claims"][0]["cards"] == ["CARD_001"]
```

- [ ] **Step 2: Run failing CLI test**

Run:

```powershell
python -m pytest tests/test_draft_source_documents_cli.py -q
```

Expected: fail because command is missing.

- [ ] **Step 3: Add parser command**

In `src/hsconfig/cli.py`, inside `_build_parser()`, add:

```python
    draft_source_documents = subparsers.add_parser("draft-source-documents")
    draft_source_documents.add_argument("--deck-name", required=True)
    draft_source_documents.add_argument("--deck-code", required=True)
    draft_source_documents.add_argument("--out", required=True)
    draft_source_documents.add_argument("--cards-json")
    draft_source_documents.add_argument("--source-evidence-json", required=True)
    draft_source_documents.add_argument("--allow-placeholder", action="store_true")
    draft_source_documents.add_argument("--json", action="store_true")
```

Add dispatch in `main()`:

```python
        elif args.command == "draft-source-documents":
            payload, code = _draft_source_documents(args)
```

- [ ] **Step 4: Implement command handler**

In `src/hsconfig/cli.py`, import:

```python
from hsconfig.source_document_drafter import draft_source_documents
```

Add:

```python
def _draft_source_documents(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty source draft output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    cards_payload = _load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    evidence_payload = read_json(args.source_evidence_json)
    evidence_rows = evidence_payload.get("evidence_rows") if isinstance(evidence_payload, dict) else evidence_payload
    if not isinstance(evidence_rows, list):
        raise ValueError("--source-evidence-json must contain evidence_rows list or a list")
    draft = draft_source_documents(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        evidence_rows=[dict(row) for row in evidence_rows if isinstance(row, dict)],
    )
    write_json(out / "source_documents.json", {"source_documents": draft["source_documents"]})
    write_json(out / "source_document_draft_report.json", draft)
    return {
        "status": "OK",
        "deck_name": args.deck_name,
        "source_documents_json": str(out / "source_documents.json"),
        "draft_summary": draft["draft_summary"],
    }, 0
```

- [ ] **Step 5: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_draft_source_documents_cli.py tests/test_cli.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_draft_source_documents_cli.py
git commit -m "Add source document drafting command"
```

---

### Task 4: Source Manifest CLI

**Files:**
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_source_manifest_cli.py`

**Interfaces:**
- Adds command: `hsconfig source-manifest --deck-name ... --deck-code ... --out ... --json`.
- Produces: `source_research_manifest.json`.

- [ ] **Step 1: Write failing source-manifest CLI test**

Add `tests/test_source_manifest_cli.py`:

```python
import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import write_json


def test_source_manifest_cli_writes_research_manifest(tmp_path: Path, capsys):
    cards_path = tmp_path / "cards.json"
    out = tmp_path / "manifest"
    write_json(cards_path, {"cards": [{"card_id": "CARD_001", "dbf_id": 1, "name": "Pirate Card", "count": 2}]})

    code = main(
        [
            "source-manifest",
            "--deck-name",
            "PirateRogue",
            "--deck-code",
            "fixture",
            "--cards-json",
            str(cards_path),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    manifest = json.loads((out / "source_research_manifest.json").read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "OK"
    assert "PirateRogue" in manifest["search_aliases"]
    assert manifest["card_targets"][0]["card_id"] == "CARD_001"
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest tests/test_source_manifest_cli.py -q
```

Expected: fail because command is missing.

- [ ] **Step 3: Add parser command and handler**

In `src/hsconfig/cli.py`, import:

```python
from hsconfig.source_research_manifest import build_source_research_manifest
```

Add parser:

```python
    source_manifest = subparsers.add_parser("source-manifest")
    source_manifest.add_argument("--deck-name", required=True)
    source_manifest.add_argument("--deck-code", required=True)
    source_manifest.add_argument("--out", required=True)
    source_manifest.add_argument("--cards-json")
    source_manifest.add_argument("--allow-placeholder", action="store_true")
    source_manifest.add_argument("--json", action="store_true")
```

Add dispatch:

```python
        elif args.command == "source-manifest":
            payload, code = _source_manifest(args)
```

Add handler:

```python
def _source_manifest(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty source manifest output directory: {out}")
    out.mkdir(parents=True, exist_ok=True)
    cards_payload = _load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    candidate_archetypes = build_candidate_archetypes(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        card_roles={},
        source_documents=[],
    )
    manifest = build_source_research_manifest(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        candidate_archetypes=candidate_archetypes,
        fixture_row=None,
    )
    write_json(out / "source_research_manifest.json", manifest)
    return {"status": "OK", "deck_name": args.deck_name, "manifest": str(out / "source_research_manifest.json")}, 0
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_source_manifest_cli.py tests/test_source_research_manifest.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_source_manifest_cli.py
git commit -m "Add source manifest command"
```

---

### Task 5: Research-Deck Evidence Shortcut

**Files:**
- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_research_deck_cli.py`

**Interfaces:**
- Adds `--source-evidence-json` to `research-deck`.
- Produces `source_document_draft_report.json` when the shortcut is used.

- [ ] **Step 1: Write failing test**

Extend `tests/test_research_deck_cli.py`:

```python
def test_research_deck_accepts_source_evidence_json(tmp_path: Path, capsys):
    from hsconfig.cli import main
    from hsconfig.io import write_json
    import json

    cards_path = tmp_path / "cards.json"
    evidence_path = tmp_path / "evidence.json"
    out = tmp_path / "research"
    write_json(cards_path, {"cards": [{"card_id": "CARD_001", "dbf_id": 1, "name": "Test Card", "count": 2}]})
    write_json(
        evidence_path,
        {
            "evidence_rows": [
                {
                    "source_url": "https://example.invalid/guide",
                    "source_title": "Guide",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-07T12:00:00Z",
                    "claim_kind": "card_role",
                    "card_mentions": ["Test Card"],
                    "stance": "core_card",
                    "evidence_text_short": "Test Card is core.",
                    "source_confidence": "high",
                }
            ]
        },
    )

    code = main(
        [
            "research-deck",
            "--deck-name",
            "TestDeck",
            "--deck-code",
            "fixture",
            "--cards-json",
            str(cards_path),
            "--source-evidence-json",
            str(evidence_path),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["source_depth_status"] == "source_backed"
    assert (out / "source_document_draft_report.json").exists()
    assert (out / "guide_sources.json").exists()
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest tests/test_research_deck_cli.py::test_research_deck_accepts_source_evidence_json -q
```

Expected: fail because `--source-evidence-json` is not accepted.

- [ ] **Step 3: Add argument and context support**

In `research_deck` parser:

```python
    research_deck.add_argument("--source-evidence-json")
```

In `_build_preconfig_context(args)`, before `_load_source_documents(...)`, add:

```python
    source_evidence_input = _load_source_evidence(getattr(args, "source_evidence_json", None))
```

Add helper:

```python
def _load_source_evidence(source_evidence_json: str | None) -> list[dict[str, Any]]:
    if source_evidence_json is None:
        return []
    payload = read_json(source_evidence_json)
    if isinstance(payload, dict):
        payload = payload.get("evidence_rows")
    if not isinstance(payload, list):
        raise ValueError("--source-evidence-json must contain a list or an object with evidence_rows")
    return [dict(row) for row in payload if isinstance(row, dict)]
```

After `deck_identity` exists and before `source_documents_input` is used, draft documents:

```python
    source_document_draft = None
    if source_evidence_input:
        source_document_draft = draft_source_documents(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            evidence_rows=source_evidence_input,
        )
        source_documents_input = list(source_document_draft["source_documents"])
```

Return `source_document_draft` in the context.

- [ ] **Step 4: Write draft report in research-deck output**

In `_research_deck(args)`, add:

```python
    if context.get("source_document_draft") is not None:
        write_json(out / "source_document_draft_report.json", context["source_document_draft"])
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m pytest tests/test_research_deck_cli.py tests/test_draft_source_documents_cli.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_research_deck_cli.py
git commit -m "Wire evidence drafting into research deck"
```

---

### Task 6: Prioritized Source Claim Gap Chains

**Files:**
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Test: `tests/test_source_claim_gap_report.py`
- Inspect: `src/hsconfig/strong_promotion_report.py`

**Interfaces:**
- Extends `build_source_claim_gap_report(...)` output with:
  - `summary.first_missing_chain`
  - `summary.next_source_builder_action`
  - per-card `priority_score`
  - per-card `priority_reason`

- [ ] **Step 1: Write failing priority test**

Extend `tests/test_source_claim_gap_report.py`:

```python
def test_source_claim_gap_report_prioritizes_mulligan_and_runtime_surface_over_generic_gap():
    report = build_source_claim_gap_report(
        deck_name="TestDeck",
        config_readiness_report={
            "cards": {
                "CARD_Z": {
                    "name": "Generic Gap",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                    "runtime_surfaces": [],
                },
                "CARD_A": {
                    "name": "Mulligan Gap",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_mulligan_claim",
                    "runtime_surfaces": [],
                },
                "CARD_B": {
                    "name": "Runtime Gap",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                    "runtime_surfaces": [],
                },
            }
        },
        claim_coverage_report={"cards": {}},
        card_behavior_plan={"rows": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    assert report["summary"]["first_missing_chain"]["card_id"] == "CARD_A"
    assert report["summary"]["next_source_builder_action"] == "add_mulligan_keep_or_discard_claim"
    assert report["cards"]["CARD_A"]["priority_score"] > report["cards"]["CARD_Z"]["priority_score"]
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest tests/test_source_claim_gap_report.py::test_source_claim_gap_report_prioritizes_mulligan_and_runtime_surface_over_generic_gap -q
```

Expected: fail because priority fields are missing.

- [ ] **Step 3: Add priority scoring**

In `src/hsconfig/source_claim_gap_report.py`, add:

```python
PRIORITY_BY_MISSING_LINK = {
    "needs_mulligan_claim": 90,
    "needs_runtime_surface": 80,
    "needs_combo_sequence": 75,
    "needs_condition_lowering": 70,
    "needs_mechanic_lowering": 65,
    "needs_guide_claim": 50,
    "none": 0,
}


def _priority_for_row(missing_link: str, row: dict[str, Any]) -> tuple[int, str]:
    base = PRIORITY_BY_MISSING_LINK.get(missing_link, 40)
    lane = str(row.get("readiness_lane", ""))
    if lane == "generic_low_confidence":
        return base, "generic_card_needs_source_claim"
    if lane == "report_only_supported":
        return base + 5, "source_claim_exists_but_cannot_lower"
    if row.get("runtime_surfaces"):
        return base - 10, "partial_runtime_surface_exists"
    return base, "first_missing_link_priority"
```

When building each row, add:

```python
        priority_score, priority_reason = _priority_for_row(missing_link, row)
```

and include:

```python
            "priority_score": priority_score,
            "priority_reason": priority_reason,
```

After rows are built:

```python
    blocked_rows = [row for row in rows.values() if row["first_missing_link"] != "none"]
    first_missing_chain = (
        max(blocked_rows, key=lambda item: (item["priority_score"], item["card_id"]))
        if blocked_rows
        else None
    )
```

Add to summary:

```python
            "first_missing_chain": first_missing_chain,
            "next_source_builder_action": (
                first_missing_chain["next_action"] if first_missing_chain is not None else "card_ready_for_strong_gate"
            ),
```

- [ ] **Step 4: Run source gap tests**

Run:

```powershell
python -m pytest tests/test_source_claim_gap_report.py tests/test_strong_promotion_report.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_claim_gap_report.py tests/test_source_claim_gap_report.py
git commit -m "Prioritize source claim gap chains"
```

---

### Task 7: Matrix Closure Summary

**Files:**
- Create: `src/hsconfig/matrix_closure.py`
- Test: `tests/test_matrix_closure.py`
- Read: `docs/operator/archetype-fixture-matrix.json`
- Read: `tests/helpers/fixture_prepare.py`

**Interfaces:**
- Consumes matrix rows and prepared fixture results.
- Produces `build_matrix_closure_summary(matrix_rows, results) -> dict[str, Any]`.

- [ ] **Step 1: Write failing tests**

Add `tests/test_matrix_closure.py`:

```python
from hsconfig.matrix_closure import build_matrix_closure_summary


def test_matrix_closure_counts_strong_and_source_informed_rows():
    summary = build_matrix_closure_summary(
        matrix_rows=[
            {"deck_name": "ShadowPriest", "fixture_stage": "core_source_backed_fixture"},
            {"deck_name": "CtAPaladin", "fixture_stage": "source_informed_valid_fixture"},
        ],
        results={
            "ShadowPriest": {
                "operator": {"technical_status": "VALID_PACKAGE", "semantic_status": "SOURCE_BACKED_STRONG"},
                "source_gap": {"summary": {"blocked_cards": 0}},
            },
            "CtAPaladin": {
                "operator": {"technical_status": "VALID_PACKAGE", "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG"},
                "source_gap": {
                    "summary": {
                        "blocked_cards": 2,
                        "first_missing_chain": {"card_id": "CARD_001", "next_action": "add_card_specific_source_claim"},
                    }
                },
            },
        },
    )

    assert summary["summary"] == {
        "deck_count": 2,
        "valid_package_count": 2,
        "source_backed_strong_count": 1,
        "source_informed_count": 1,
        "blocked_card_count": 2,
    }
    assert summary["decks"]["CtAPaladin"]["first_missing_chain"]["card_id"] == "CARD_001"
```

- [ ] **Step 2: Run failing test**

Run:

```powershell
python -m pytest tests/test_matrix_closure.py -q
```

Expected: fail because module is missing.

- [ ] **Step 3: Implement matrix closure module**

Create `src/hsconfig/matrix_closure.py`:

```python
from __future__ import annotations

from typing import Any


def build_matrix_closure_summary(
    *,
    matrix_rows: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    decks: dict[str, dict[str, Any]] = {}
    valid_package_count = 0
    strong_count = 0
    source_informed_count = 0
    blocked_card_count = 0

    for row in matrix_rows:
        deck_name = str(row.get("deck_name", ""))
        result = results.get(deck_name, {})
        operator = result.get("operator", {})
        source_gap = result.get("source_gap", {})
        gap_summary = source_gap.get("summary", {}) if isinstance(source_gap, dict) else {}
        technical_status = str(operator.get("technical_status", ""))
        semantic_status = str(operator.get("semantic_status", ""))
        blocked_cards = int(gap_summary.get("blocked_cards", 0))
        valid_package_count += int(technical_status == "VALID_PACKAGE")
        strong_count += int(semantic_status == "SOURCE_BACKED_STRONG")
        source_informed_count += int(semantic_status == "VALID_BUT_NOT_GUIDE_STRONG")
        blocked_card_count += blocked_cards
        decks[deck_name] = {
            "fixture_stage": str(row.get("fixture_stage", "")),
            "technical_status": technical_status,
            "semantic_status": semantic_status,
            "blocked_cards": blocked_cards,
            "first_missing_chain": gap_summary.get("first_missing_chain"),
        }

    return {
        "schema_version": 1,
        "summary": {
            "deck_count": len(matrix_rows),
            "valid_package_count": valid_package_count,
            "source_backed_strong_count": strong_count,
            "source_informed_count": source_informed_count,
            "blocked_card_count": blocked_card_count,
        },
        "decks": decks,
    }
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_matrix_closure.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/matrix_closure.py tests/test_matrix_closure.py
git commit -m "Add matrix closure summary"
```

---

### Task 8: 11-Deck Source Builder Matrix Regression

**Files:**
- Create: `tests/test_source_builder_matrix_closure.py`
- Modify: `docs/operator/archetype-fixture-matrix.json` only if a row lacks the intended decision-family metadata.
- Uses: `tests/helpers/fixture_prepare.py`

**Interfaces:**
- Proves all 11 rows have source fixtures and produce a closure summary.

- [ ] **Step 1: Write matrix closure regression**

Add `tests/test_source_builder_matrix_closure.py`:

```python
import json
from pathlib import Path

from hsconfig.matrix_closure import build_matrix_closure_summary
from tests.helpers.fixture_prepare import prepare_fixture


ROOT = Path(__file__).resolve().parents[1]


def test_all_matrix_rows_have_source_fixture_files():
    matrix = json.loads((ROOT / "docs" / "operator" / "archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    missing = []
    for row in matrix["decks"]:
        fixture_name = f"source_documents_{row['deck_name'].lower()}_strong.json"
        if not (ROOT / "tests" / "fixtures" / fixture_name).exists():
            missing.append(fixture_name)
    assert missing == []


def test_matrix_closure_summary_is_machine_readable(tmp_path: Path):
    matrix = json.loads((ROOT / "docs" / "operator" / "archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    rows = matrix["decks"]
    results = {}
    for row in rows:
        prepared = prepare_fixture(tmp_path, row["deck_name"])
        results[row["deck_name"]] = {
            "operator": prepared["operator"],
            "source_gap": prepared["source_gap"],
        }

    summary = build_matrix_closure_summary(matrix_rows=rows, results=results)

    assert summary["summary"]["deck_count"] == 11
    assert summary["summary"]["valid_package_count"] == 11
    assert summary["summary"]["source_backed_strong_count"] >= 4
    assert set(summary["decks"]) == {row["deck_name"] for row in rows}
```

- [ ] **Step 2: Run failing or passing regression**

Run:

```powershell
python -m pytest tests/test_source_builder_matrix_closure.py -q
```

Expected: pass if helpers already expose `source_gap`; fail with a missing key if helper output needs a small extension.

- [ ] **Step 3: Extend fixture helper when needed**

If `prepare_fixture(...)` lacks `source_gap`, update `tests/helpers/fixture_prepare.py` to read:

```python
source_gap = read_json(reports / "source_claim_gap_report.json")
return {
    "operator": operator,
    "readiness": readiness,
    "source_gap": source_gap,
    "package": out,
}
```

Keep existing returned keys intact.

- [ ] **Step 4: Run matrix tests**

Run:

```powershell
python -m pytest tests/test_source_builder_matrix_closure.py tests/test_strong_fixture_closure.py tests/test_archetype_fixture_matrix.py -q
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_source_builder_matrix_closure.py tests/helpers/fixture_prepare.py docs/operator/archetype-fixture-matrix.json
git commit -m "Add source builder matrix closure regression"
```

---

### Task 9: Operator Docs And Skill Workflow

**Files:**
- Create: `docs/operator/source-builder-workflow.md`
- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Test: `tests/test_skill_files.py`

**Interfaces:**
- User-facing normal path becomes:
  1. `source-manifest`
  2. Codex/source research into short evidence rows
  3. `draft-source-documents`
  4. `research-deck`
  5. `prepare`
  6. `operator_summary`
  7. `apply` only through gate

- [ ] **Step 1: Write failing docs test**

Extend `tests/test_skill_files.py`:

```python
def test_skill_documents_source_builder_lite_workflow():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    skill = (root / ".agents" / "skills" / "hsconfig" / "SKILL.md").read_text(encoding="utf-8")
    workflow = (root / ".agents" / "skills" / "hsconfig" / "references" / "workflow.md").read_text(encoding="utf-8")
    operator = (root / "docs" / "operator" / "source-builder-workflow.md").read_text(encoding="utf-8")

    combined = "\n".join([skill, workflow, operator])
    assert "source-manifest" in combined
    assert "draft-source-documents" in combined
    assert "source_documents.json" in combined
    assert "operator_summary.json" in combined
    assert "Presume.json" not in operator
    assert "Concede.json" not in operator
```

- [ ] **Step 2: Run failing docs test**

Run:

```powershell
python -m pytest tests/test_skill_files.py::test_skill_documents_source_builder_lite_workflow -q
```

Expected: fail because the new operator doc is missing.

- [ ] **Step 3: Add operator workflow doc**

Create `docs/operator/source-builder-workflow.md`:

```markdown
# Source Builder Workflow

HSConfig builds pre-game HearthRanger VisionAI CustomConfig packages. It does not parse replays, inspect winrate, or tune from post-game logs.

Normal path:

1. Run `hsconfig source-manifest` to get deck aliases, card targets, and research questions.
2. Use Codex research to collect short evidence rows from current guide, mulligan, card-text, and metadata sources.
3. Run `hsconfig draft-source-documents` to convert evidence rows into `source_documents.json`.
4. Run `hsconfig research-deck --source-documents-json ...` to normalize guide sources.
5. Run `hsconfig prepare --guide-sources-json ...` to compile the package.
6. Read `reports/operator_summary.json` first.
7. Run `hsconfig apply` only when the apply gate allows it or the operator intentionally uses `--allow-source-informed`.

Evidence rows should be short and atomic. Long guide prose belongs outside runtime config.

Every card should reach one visible lane: `guide_backed`, `source_backed_static_semantics`, `archetype_inferred`, `explicit_low_confidence`, `generic_low_confidence`, or `contract_gap`.
```

- [ ] **Step 4: Update README and skill references**

In `README.md`, add this short command block under the normal path:

```powershell
hsconfig source-manifest --deck-name "ShadowPriest" --deck-code "<deck code>" --out ".\outputs\shadowpriest\manifest" --json
hsconfig draft-source-documents --deck-name "ShadowPriest" --deck-code "<deck code>" --source-evidence-json ".\source_evidence.json" --out ".\outputs\shadowpriest\source" --json
hsconfig research-deck --deck-name "ShadowPriest" --deck-code "<deck code>" --source-documents-json ".\outputs\shadowpriest\source\source_documents.json" --out ".\outputs\shadowpriest\research" --json
hsconfig prepare --deck-name "ShadowPriest" --deck-code "<deck code>" --guide-sources-json ".\outputs\shadowpriest\research\guide_sources.json" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest\package" --json
```

In `.agents/skills/hsconfig/SKILL.md`, update normal workflow to include `source-manifest` and `draft-source-documents` before `research-deck`.

In `.agents/skills/hsconfig/references/workflow.md`, add the same path and keep `operator_summary.json` as the gate.

- [ ] **Step 5: Sync installed skill**

Run:

```powershell
python scripts\sync_installed_skill.py
python scripts\sync_installed_skill.py --check
```

Expected: second command prints `HSConfig skill is in sync`.

- [ ] **Step 6: Run docs tests**

Run:

```powershell
python -m pytest tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add README.md docs/operator/source-builder-workflow.md .agents/skills/hsconfig tests/test_skill_files.py
git add C:\Users\darbo\.codex\skills\hsconfig
git commit -m "Document source builder workflow"
```

---

### Task 10: Active Research Audit Refresh

**Files:**
- Create: `docs/research/2026-07-07-hsconfig-source-builder-lite/outline.yaml`
- Create: `docs/research/2026-07-07-hsconfig-source-builder-lite/fields.yaml`
- Output: `docs/research/2026-07-07-hsconfig-source-builder-lite/results/*.json`
- Test: `tests/test_research_audit_schema.py`

**Interfaces:**
- Uses the local `research-deep` workflow and validates every result JSON with `validate_json.py`.

- [ ] **Step 1: Create fields file**

Create `docs/research/2026-07-07-hsconfig-source-builder-lite/fields.yaml`:

```yaml
field_categories:
  - category: audit
    fields:
      - name: source_summary
        required: true
      - name: current_truth
        required: true
      - name: repo_alignment
        required: true
      - name: implementation_implication
        required: true
      - name: gaps_or_risks
        required: true
      - name: recommended_action
        required: true
      - name: confidence
        required: true
      - name: citations
        required: true
      - name: uncertain
        required: true
```

- [ ] **Step 2: Create outline**

Create `docs/research/2026-07-07-hsconfig-source-builder-lite/outline.yaml`:

```yaml
topic: hsconfig-source-builder-lite-2026-07-07
execution:
  output_dir: C:\Users\darbo\Documents\HSConfig\docs\research\2026-07-07-hsconfig-source-builder-lite\results
  batch_size: 5
  items_per_agent: 1
items:
  - name: Evidence Row Contract
    category: HSConfig source builder
    description: >
      Audit whether short evidence rows are the right boundary between Codex online research and deterministic HSConfig source_documents generation.
  - name: Source Document Claim Strictness
    category: Runtime safety
    description: >
      Audit claim_kind, card resolution, claim confidence, freshness, and report-only handling before runtime lowering.
  - name: Eleven Deck Strongness Closure
    category: Fixture matrix
    description: >
      Audit whether the 11-deck matrix is sufficient for source-builder closure and which families remain weak.
  - name: VisionAI Runtime Lowering Surface
    category: HearthRanger VisionAI
    description: >
      Audit documented CardID, Mulligan, Combo, and GlobalValues surfaces that source claims may lower into.
  - name: Lean Skill Workflow
    category: Operator UX
    description: >
      Audit whether the new source-builder workflow remains simple enough for the local hsconfig skill.
```

- [ ] **Step 3: Run research-deep**

From `C:\Users\darbo\Documents\HSConfig`, run the local `research-deep` workflow against that outline. Each item must write one JSON result into the configured `results` folder and pass validation.

Expected result files:

```text
Evidence_Row_Contract.json
Source_Document_Claim_Strictness.json
Eleven_Deck_Strongness_Closure.json
VisionAI_Runtime_Lowering_Surface.json
Lean_Skill_Workflow.json
```

- [ ] **Step 4: Validate research JSON**

Run:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-07-hsconfig-source-builder-lite\fields.yaml -d docs\research\2026-07-07-hsconfig-source-builder-lite\results -q
```

Expected: `Validation passed: 5/5`.

- [ ] **Step 5: Add schema regression**

If `tests/test_research_audit_schema.py` already validates all research folders, no change is needed. If it does not include the new folder automatically, add:

```python
def test_source_builder_lite_research_results_validate():
    from pathlib import Path
    import subprocess

    root = Path(__file__).resolve().parents[1]
    fields = root / "docs" / "research" / "2026-07-07-hsconfig-source-builder-lite" / "fields.yaml"
    results = root / "docs" / "research" / "2026-07-07-hsconfig-source-builder-lite" / "results"
    completed = subprocess.run(
        [
            "python",
            str(Path.home() / ".codex" / "skills" / "research" / "validate_json.py"),
            "-f",
            str(fields),
            "-d",
            str(results),
            "-q",
        ],
        cwd=root,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
```

- [ ] **Step 6: Commit**

```powershell
git add docs/research/2026-07-07-hsconfig-source-builder-lite tests/test_research_audit_schema.py
git commit -m "Add source builder lite research audit"
```

---

### Task 11: Full Workflow Verification

**Files:**
- No product code changes.
- Uses tests and generated temp outputs only.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m pytest tests/test_source_research_manifest.py tests/test_source_document_drafter.py tests/test_draft_source_documents_cli.py tests/test_source_manifest_cli.py tests/test_research_deck_cli.py tests/test_source_claim_gap_report.py tests/test_matrix_closure.py tests/test_source_builder_matrix_closure.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run existing gate and fixture tests**

Run:

```powershell
python -m pytest tests/test_apply_gate.py tests/test_runtime_apply.py tests/test_strong_fixture_closure.py tests/test_archetype_fixture_e2e.py tests/test_depth_matrix_e2e.py -q
```

Expected: all selected tests pass; existing skip count remains acceptable for non-core fixture rows.

- [ ] **Step 3: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes.

- [ ] **Step 4: Run skill sync check**

Run:

```powershell
python scripts\sync_installed_skill.py --check
```

Expected: `HSConfig skill is in sync`.

- [ ] **Step 5: Check docs for stale active-path claims**

Run:

```powershell
rg -n "default-only mulligan|guide source as merely optional|post-game tuning owned by HSConfig|normal-path Presume|normal-path Concede" README.md docs\operator .agents\skills\hsconfig C:\Users\darbo\.codex\skills\hsconfig
```

Expected: no active-doc matches.

- [ ] **Step 6: Check git state**

Run:

```powershell
git status --short --branch
git log --oneline -5
```

Expected: branch is on `main`; pending changes are only intentional code/docs/tests if commits were deferred.

---

### Task 12: GitHub Update

**Files:**
- All files changed by prior tasks.

- [ ] **Step 1: Review diff**

Run:

```powershell
git diff --stat
git diff -- src tests docs README.md .agents
```

Expected: diff only covers source-builder-lite code, tests, docs, and skill sync.

- [ ] **Step 2: Commit remaining changes when previous tasks were not individually committed**

Run:

```powershell
git add README.md docs src tests .agents
git add C:\Users\darbo\.codex\skills\hsconfig
git commit -m "Add autonomous source builder lite workflow"
```

Expected: commit succeeds or prints no changes if every task already committed.

- [ ] **Step 3: Push main**

Run:

```powershell
git push origin main
```

Expected: push succeeds and `origin/main` contains the new workflow.

- [ ] **Step 4: Final status**

Run:

```powershell
git status --short --branch
```

Expected: `## main...origin/main` with no changed files.

---

## Final Acceptance Criteria

- `hsconfig source-manifest` writes source research instructions for a deck.
- `hsconfig draft-source-documents` converts short evidence rows into strict `source_documents.json`.
- `hsconfig research-deck --source-evidence-json ...` drafts documents and writes normal research artifacts.
- `source_claim_gap_report.json` exposes a prioritized first missing chain and source-builder next action.
- The 11-deck matrix has a machine-readable closure summary.
- Docs and installed skill show the same normal path.
- Apply gate behavior remains unchanged and fail-closed.
- Full pytest suite passes.
- `python scripts\sync_installed_skill.py --check` passes.
- `git status --short --branch` is clean on `main...origin/main` after push.

# HSConfig Research Contract Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a lean pre-build research contract layer so HSConfig can turn deck input plus guide/static card semantics into explicit, machine-readable config intent before it writes `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json`.

**Architecture:** Add a focused `research_contract.py` module that converts decoded deck identity, enriched card metadata, and normalized guide claims into stable artifacts: `archetype_research.json`, `claims.json`, `card_role_map.json`, `mulligan_anchor_map.json`, `card_usage_expectations.json`, `known_bad_patterns.json`, and `globalvalue_intent.json`. Keep `build` compatible, add a normal `prepare` command as the one-shot deck-to-package path, and add a diagnostic `research-contract` command for contract-only review. Do not add replay parsing, HDT parsing, winrate, HSTuner sessions, or post-game tuning.

**Tech Stack:** Python 3.11+, `argparse`, existing `hearthstone.deckstrings`, existing HSConfig modules, `pytest`, strict JSON reports under `outputs/<deck_slug>/reports/`.

---

## File Structure

Create:

- `src/hsconfig/research_contract.py` - builds and writes the research bundle.
- `tests/test_research_contract.py` - unit tests for artifact shape, confidence lanes, static semantics, guide claims, and bad patterns.
- `tests/test_prepare_cli.py` - CLI tests for `research-contract` and `prepare`.

Modify:

- `src/hsconfig/cli.py` - add `research-contract` and `prepare`; refactor `_build` enough to reuse the same pipeline without copying compiler logic.
- `src/hsconfig/gameplan_contract.py` - accept research-bundle-shaped source claims and preserve confidence lanes in the gameplan contract.
- `tests/test_cli.py` - assert `build` keeps backwards compatibility and writes research-bundle reports.
- `tests/test_shadowpriest_e2e.py` - assert ShadowPriest `prepare` produces hero-power semantics, research artifacts, validation, and apply readiness.
- `README.md` - make `prepare` the normal command while preserving `build`, `validate`, and `apply` as explicit surfaces.
- `.agents/skills/hsconfig/SKILL.md` - update the skill workflow to use `prepare` as the default deck-to-config command.
- `.agents/skills/hsconfig/references/workflow.md` - document `prepare`, `research-contract`, `build`, `validate`, and `apply`.
- `.agents/skills/hsconfig/references/guide-research-policy.md` - document confidence lanes and source fields.

Leave untouched:

- HSTuner, replay parsing, HDT parsing, winrate validation, runtime logs, candidate promotion, and post-run patching.
- Normal-path `Presume.json` and `Concede.json`; they remain out of scope.

---

### Task 1: Add Research Contract Unit Tests

**Files:**

- Create: `tests/test_research_contract.py`
- Read: `src/hsconfig/guide_research.py`
- Read: `src/hsconfig/gameplan_contract.py`

- [ ] **Step 1: Create failing tests for the bundle shape**

Create `tests/test_research_contract.py` with this content:

```python
from hsconfig.guide_research import normalize_source_claims
from hsconfig.research_contract import build_research_contract_bundle


def test_research_contract_emits_all_operator_artifacts():
    deck_identity = {
        "deck_name": "Fixture Aggro",
        "deck_slug": "fixture_aggro",
        "cards": [
            {"card_id": "EX1_001", "count": 2, "name": "Pressure One"},
            {"card_id": "EX1_002", "count": 1, "name": "Burst Two"},
            {"card_id": "EX1_003", "count": 1, "name": "Expensive Three"},
        ],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "EX1_001",
                "name": "Pressure One",
                "mechanic_families": ["battlecry", "damage"],
                "semantic_families": ["battlecry", "damage"],
            },
            {
                "card_id": "EX1_002",
                "name": "Burst Two",
                "mechanic_families": ["damage"],
                "semantic_families": ["damage"],
            },
            {
                "card_id": "EX1_003",
                "name": "Expensive Three",
                "mechanic_families": ["draw"],
                "semantic_families": ["draw"],
            },
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/fixture-guide",
                "claim": "Always keep Pressure One and push face damage early.",
                "cards": ["EX1_001"],
                "claim_type": "mulligan_and_gameplan",
                "retrieved_at": "2026-07-05",
            },
            {
                "source": "guide",
                "url": "https://example.invalid/fixture-guide",
                "claim": "Use Pressure One with Burst Two for a combo burst turn.",
                "cards": ["EX1_001", "EX1_002"],
                "claim_type": "combo",
                "values": ["8", "14"],
            },
            {
                "source": "guide",
                "url": "https://example.invalid/fixture-guide",
                "claim": "Never keep Expensive Three in the opener.",
                "cards": ["EX1_003"],
                "claim_type": "bad_pattern",
            },
        ]
    )

    bundle = build_research_contract_bundle(deck_identity, card_metadata, source_claims)

    assert set(bundle) == {
        "archetype_research",
        "claims",
        "card_role_map",
        "mulligan_anchor_map",
        "card_usage_expectations",
        "known_bad_patterns",
        "globalvalue_intent",
        "coverage_summary",
    }
    assert bundle["archetype_research"]["deck_name"] == "Fixture Aggro"
    assert bundle["archetype_research"]["confidence"] == "guide_backed"
    assert bundle["coverage_summary"]["deck_card_count"] == 3
    assert bundle["coverage_summary"]["guide_backed_card_count"] == 3
    assert bundle["card_role_map"]["EX1_001"]["confidence"] == "guide_backed"
    assert "pressure" in bundle["card_role_map"]["EX1_001"]["roles"]
    assert bundle["mulligan_anchor_map"]["EX1_001"]["intent"] == "hold"
    assert bundle["mulligan_anchor_map"]["EX1_003"]["intent"] == "avoid"
    assert bundle["card_usage_expectations"]["EX1_002"]["expected_use"] == "combo_burst_piece"
    assert bundle["known_bad_patterns"][0]["card_id"] == "EX1_003"
    assert bundle["globalvalue_intent"]["pressure_bias"] == "high"


def test_research_contract_uses_static_semantics_without_guide_claims():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "cards": [{"card_id": "SW_448", "count": 1}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
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
            }
        ]
    }

    bundle = build_research_contract_bundle(deck_identity, card_metadata, {"claims": []})

    assert bundle["archetype_research"]["confidence"] == "source_backed_static_semantics"
    assert bundle["card_role_map"]["SW_448"]["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in bundle["card_role_map"]["SW_448"]["roles"]
    assert bundle["card_usage_expectations"]["SW_448"]["expected_use"] == (
        "start_of_game_shadowform_enables_hero_power_pressure"
    )
    assert bundle["globalvalue_intent"]["overlays"]["MyHeroPowerValue"] == "increase"
    assert "Mind Spike" in bundle["globalvalue_intent"]["overlay_reasons"]["MyHeroPowerValue"]


def test_research_contract_marks_uncovered_cards_explicitly():
    deck_identity = {
        "deck_name": "Uncovered",
        "deck_slug": "uncovered",
        "cards": [{"card_id": "EX1_999", "count": 1}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_999", "name": "Unknown Card"}]}

    bundle = build_research_contract_bundle(deck_identity, card_metadata, {"claims": []})

    assert bundle["archetype_research"]["confidence"] == "generic_low_confidence"
    assert bundle["card_role_map"]["EX1_999"]["confidence"] == "generic_low_confidence"
    assert bundle["card_usage_expectations"]["EX1_999"]["expected_use"] == "follow_archetype_plan"
    assert bundle["coverage_summary"]["generic_low_confidence_card_count"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_research_contract.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.research_contract'`.

- [ ] **Step 3: Keep the failing test uncommitted until green**

Do not commit a deliberately failing intermediate state on `main`. Continue directly to Task 2 and commit the red/green slice together after the implementation passes.

---

### Task 2: Implement Research Contract Builder

**Files:**

- Create: `src/hsconfig/research_contract.py`
- Test: `tests/test_research_contract.py`

- [ ] **Step 1: Create the implementation module**

Create `src/hsconfig/research_contract.py` with this content:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.guide_research import normalize_source_claims
from hsconfig.io import write_json


NEGATIVE_KEEP_MARKERS = (
    "never keep",
    "do not keep",
    "don't keep",
    "dont keep",
    "avoid keeping",
    "avoid keep",
)


def build_research_contract_bundle(
    deck_identity: dict[str, Any],
    card_metadata: dict[str, Any] | list[dict[str, Any]],
    source_claims: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, Any]:
    cards = _deck_cards(deck_identity)
    metadata_by_card = _metadata_by_card(card_metadata)
    claims_payload = _coerce_source_claims(source_claims)
    claims = claims_payload["claims"]
    claims_by_card = _claims_by_card(claims)

    card_role_map: dict[str, dict[str, Any]] = {}
    mulligan_anchor_map: dict[str, dict[str, Any]] = {}
    card_usage_expectations: dict[str, dict[str, Any]] = {}
    known_bad_patterns: list[dict[str, Any]] = []

    for card in cards:
        card_id = str(card["card_id"])
        metadata = metadata_by_card.get(card_id, {})
        related_claims = claims_by_card.get(card_id, [])
        semantic_families = _semantic_families(card, metadata)
        roles = _roles_from_claims_and_semantics(semantic_families, related_claims)
        confidence = _confidence_for_card(related_claims, semantic_families)
        source_claim_ids = [str(claim["claim_id"]) for claim in related_claims]
        linked_entities = list(metadata.get("linked_entities", []))

        card_role_map[card_id] = {
            "card_id": card_id,
            "name": metadata.get("name", card.get("name", card_id)),
            "count": int(card.get("count", metadata.get("count", 1))),
            "roles": roles,
            "semantic_families": semantic_families,
            "linked_entities": linked_entities,
            "confidence": confidence,
            "source_claim_ids": source_claim_ids,
        }
        mulligan_anchor_map[card_id] = _mulligan_intent(card_id, related_claims, roles, confidence)
        card_usage_expectations[card_id] = {
            "card_id": card_id,
            "expected_use": _expected_use(roles, related_claims),
            "confidence": confidence,
            "source_claim_ids": source_claim_ids,
        }
        for claim in related_claims:
            if _is_bad_pattern(claim):
                known_bad_patterns.append(
                    {
                        "card_id": card_id,
                        "claim_id": claim["claim_id"],
                        "pattern": str(claim.get("claim", "")),
                        "source_claim_ids": [claim["claim_id"]],
                    }
                )

    globalvalue_intent = _globalvalue_intent(card_role_map)
    coverage_summary = _coverage_summary(card_role_map)
    archetype_research = {
        "deck_name": str(deck_identity.get("deck_name", "Deck")),
        "deck_slug": str(deck_identity.get("deck_slug", "")),
        "archetype": _archetype(card_role_map),
        "confidence": _deck_confidence(coverage_summary),
        "source_claim_count": len(claims),
        "source_claim_ids": [str(claim["claim_id"]) for claim in claims],
    }

    return {
        "archetype_research": archetype_research,
        "claims": claims,
        "card_role_map": dict(sorted(card_role_map.items())),
        "mulligan_anchor_map": dict(sorted(mulligan_anchor_map.items())),
        "card_usage_expectations": dict(sorted(card_usage_expectations.items())),
        "known_bad_patterns": sorted(
            known_bad_patterns, key=lambda row: (row["card_id"], row["claim_id"])
        ),
        "globalvalue_intent": globalvalue_intent,
        "coverage_summary": coverage_summary,
    }


def write_research_contract_bundle(bundle: dict[str, Any], reports_dir: Path) -> None:
    research_dir = reports_dir / "research"
    write_json(research_dir / "archetype_research.json", bundle["archetype_research"])
    write_json(research_dir / "claims.json", {"claims": bundle["claims"]})
    write_json(research_dir / "card_role_map.json", bundle["card_role_map"])
    write_json(research_dir / "mulligan_anchor_map.json", bundle["mulligan_anchor_map"])
    write_json(research_dir / "card_usage_expectations.json", bundle["card_usage_expectations"])
    write_json(research_dir / "known_bad_patterns.json", bundle["known_bad_patterns"])
    write_json(research_dir / "globalvalue_intent.json", bundle["globalvalue_intent"])
    write_json(research_dir / "coverage_summary.json", bundle["coverage_summary"])


def _deck_cards(deck_identity: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(
        (dict(card) for card in deck_identity.get("cards", [])),
        key=lambda card: str(card["card_id"]),
    )


def _metadata_by_card(card_metadata: dict[str, Any] | list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows = card_metadata.get("cards", []) if isinstance(card_metadata, dict) else card_metadata
    return {str(row["card_id"]): dict(row) for row in rows}


def _coerce_source_claims(source_claims: dict[str, Any] | list[dict[str, Any]] | None) -> dict[str, Any]:
    if source_claims is None:
        return {"claims": [], "claim_count": 0}
    if isinstance(source_claims, list):
        return normalize_source_claims(source_claims)
    claims = [dict(claim) for claim in source_claims.get("claims", [])]
    if not all("claim_id" in claim for claim in claims):
        return normalize_source_claims(claims)
    for claim in claims:
        claim.setdefault("cards", [])
        claim["cards"] = list(dict.fromkeys(str(card) for card in claim.get("cards", [])))
        claim.setdefault("claim_type", "general")
        claim.setdefault("confidence", "source_backed")
        claim.setdefault("source_refs", [])
    return {"claims": sorted(claims, key=lambda claim: str(claim["claim_id"])), "claim_count": len(claims)}


def _claims_by_card(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_card: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        for card_id in claim.get("cards", []):
            by_card.setdefault(str(card_id), []).append(claim)
    return by_card


def _semantic_families(card: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    values = {
        str(item)
        for item in [
            *metadata.get("mechanic_families", card.get("mechanic_families", [])),
            *metadata.get("semantic_families", card.get("semantic_families", [])),
        ]
    }
    return sorted(item for item in values if item)


def _roles_from_claims_and_semantics(
    semantic_families: list[str],
    claims: list[dict[str, Any]],
) -> list[str]:
    text = _claim_text(claims)
    claim_types = {str(claim.get("claim_type", "")).lower() for claim in claims}
    roles = set(semantic_families)
    if "keep" in text and not _has_negative_keep(text):
        roles.add("mulligan_anchor")
    if any(marker in text for marker in ("face", "damage", "pressure", "push", "burst")):
        roles.add("pressure")
    if "combo" in claim_types or "combo" in text:
        roles.add("combo_piece")
    if "hero_power_transform" in roles or "hero_power_pressure" in roles:
        roles.add("pressure")
    return sorted(roles) or ["deck_card"]


def _confidence_for_card(claims: list[dict[str, Any]], semantic_families: list[str]) -> str:
    if claims:
        if any(_is_guide_claim(claim) for claim in claims):
            return "guide_backed"
        return "source_backed"
    if {"hero_power_transform", "hero_power_pressure", "start_of_game", "shadowform"} & set(
        semantic_families
    ):
        return "source_backed_static_semantics"
    if semantic_families:
        return "archetype_inferred"
    return "generic_low_confidence"


def _is_guide_claim(claim: dict[str, Any]) -> bool:
    if str(claim.get("confidence")) == "guide_backed":
        return True
    source = str(claim.get("source", "")).lower()
    url = str(claim.get("url", "")).lower()
    source_title = str(claim.get("source_title", "")).lower()
    return "guide" in source or "guide" in url or "guide" in source_title


def _mulligan_intent(
    card_id: str,
    claims: list[dict[str, Any]],
    roles: list[str],
    confidence: str,
) -> dict[str, Any]:
    text = _claim_text(claims)
    if _has_negative_keep(text):
        intent = "avoid"
    elif "mulligan_anchor" in roles:
        intent = "hold"
    else:
        intent = "neutral"
    return {
        "card_id": card_id,
        "intent": intent,
        "condition": "*",
        "confidence": confidence,
        "source_claim_ids": [str(claim["claim_id"]) for claim in claims],
    }


def _expected_use(roles: list[str], claims: list[dict[str, Any]]) -> str:
    text = _claim_text(claims)
    if "hero_power_transform" in roles and "hero_power_pressure" in roles:
        return "start_of_game_shadowform_enables_hero_power_pressure"
    if "combo_piece" in roles and "pressure" in roles:
        return "combo_burst_piece"
    if "mulligan_anchor" in roles and "pressure" in roles:
        return "keep_and_pressure"
    if "mulligan_anchor" in roles:
        return "keep_and_play_on_plan"
    if _has_negative_keep(text):
        return "avoid_low_value_timing"
    if "pressure" in roles:
        return "prioritize_for_pressure"
    return "follow_archetype_plan"


def _globalvalue_intent(card_role_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    all_roles = {role for row in card_role_map.values() for role in row.get("roles", [])}
    overlays: dict[str, str] = {}
    overlay_reasons: dict[str, str] = {}
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
    if "hero_power_transform" in all_roles or "hero_power_pressure" in all_roles:
        overlays["MyHeroPowerValue"] = "increase"
        overlay_reasons["MyHeroPowerValue"] = _hero_power_reason(card_role_map)
    return {
        "pressure_bias": "high" if overlays else "baseline",
        "overlays": dict(sorted(overlays.items())),
        "overlay_reasons": dict(sorted(overlay_reasons.items())),
    }


def _hero_power_reason(card_role_map: dict[str, dict[str, Any]]) -> str:
    for row in card_role_map.values():
        for linked in row.get("linked_entities", []):
            if linked.get("card_id") == "EX1_625t" or linked.get("name") == "Mind Spike":
                return f"{row.get('name', row['card_id'])} enables Mind Spike as pressure damage."
    return "Hero Power pressure is part of this deck plan."


def _coverage_summary(card_role_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = {
        "guide_backed": 0,
        "source_backed_static_semantics": 0,
        "archetype_inferred": 0,
        "generic_low_confidence": 0,
    }
    for row in card_role_map.values():
        counts[str(row["confidence"])] += 1
    return {
        "deck_card_count": len(card_role_map),
        "guide_backed_card_count": counts["guide_backed"],
        "source_backed_static_semantics_card_count": counts["source_backed_static_semantics"],
        "archetype_inferred_card_count": counts["archetype_inferred"],
        "generic_low_confidence_card_count": counts["generic_low_confidence"],
    }


def _deck_confidence(summary: dict[str, Any]) -> str:
    if summary["deck_card_count"] == summary["guide_backed_card_count"]:
        return "guide_backed"
    if summary["guide_backed_card_count"] > 0:
        return "mixed"
    if summary["source_backed_static_semantics_card_count"] > 0:
        return "source_backed_static_semantics"
    if summary["archetype_inferred_card_count"] > 0:
        return "archetype_inferred"
    return "generic_low_confidence"


def _archetype(card_role_map: dict[str, dict[str, Any]]) -> str:
    roles = {role for row in card_role_map.values() for role in row.get("roles", [])}
    if "pressure" in roles or "damage" in roles or "combo_piece" in roles:
        return "aggressive_gameplan"
    return "unknown_archetype"


def _is_bad_pattern(claim: dict[str, Any]) -> bool:
    claim_type = str(claim.get("claim_type", "")).lower()
    text = str(claim.get("claim", "")).lower()
    return claim_type in {"bad_pattern", "known_bad_pattern"} or any(
        marker in text for marker in ("never", "avoid", "do not", "don't", "dont")
    )


def _claim_text(claims: list[dict[str, Any]]) -> str:
    return " ".join(str(claim.get("claim", "")) for claim in claims).lower()


def _has_negative_keep(text: str) -> bool:
    return any(marker in text for marker in NEGATIVE_KEEP_MARKERS)
```

- [ ] **Step 2: Run the research contract tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_research_contract.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit the implementation**

```powershell
git add src/hsconfig/research_contract.py tests/test_research_contract.py
git commit -m "feat: build research contract bundle"
```

---

### Task 3: Write Research Bundle During Build

**Files:**

- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing build assertions**

In `tests/test_cli.py`, extend `test_build_accepts_claims_json_for_guide_backed_config` after `payload = json.loads(captured.out)`:

```python
    research_dir = out / "reports" / "research"
    archetype_research = json.loads(
        (research_dir / "archetype_research.json").read_text(encoding="utf-8")
    )
    card_role_map = json.loads((research_dir / "card_role_map.json").read_text(encoding="utf-8"))
    mulligan_anchor_map = json.loads(
        (research_dir / "mulligan_anchor_map.json").read_text(encoding="utf-8")
    )
    globalvalue_intent = json.loads(
        (research_dir / "globalvalue_intent.json").read_text(encoding="utf-8")
    )
```

Add these assertions before the final assertion block ends:

```python
    assert archetype_research["confidence"] == "guide_backed"
    assert card_role_map["EX1_001"]["confidence"] == "guide_backed"
    assert mulligan_anchor_map["EX1_001"]["intent"] == "hold"
    assert globalvalue_intent["pressure_bias"] == "high"
```

- [ ] **Step 2: Run the focused CLI test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_cli.py::test_build_accepts_claims_json_for_guide_backed_config -q
```

Expected: FAIL because `reports/research/archetype_research.json` does not exist.

- [ ] **Step 3: Wire bundle creation into `_build`**

In `src/hsconfig/cli.py`, add this import:

```python
from hsconfig.research_contract import build_research_contract_bundle, write_research_contract_bundle
```

After `source_claims = normalize_source_claims(claims)`, add:

```python
    research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=source_claims,
    )
```

After writing `semantic_enrichment_report.json` and `card_semantic_audit.md`, add:

```python
    write_research_contract_bundle(research_bundle, reports_dir)
```

Do not change the existing `gameplan_contract = build_gameplan_contract(...)` call in this task. The first integration step is artifact visibility, not a compiler rewrite.

- [ ] **Step 4: Run the focused CLI test**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_cli.py::test_build_accepts_claims_json_for_guide_backed_config -q
```

Expected: PASS.

- [ ] **Step 5: Run research and CLI tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_research_contract.py tests/test_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_cli.py
git commit -m "feat: emit research contract reports during build"
```

---

### Task 4: Add `research-contract` Diagnostic Command

**Files:**

- Modify: `src/hsconfig/cli.py`
- Create: `tests/test_prepare_cli.py`

- [ ] **Step 1: Add failing CLI test for contract-only output**

Create `tests/test_prepare_cli.py` with this content:

```python
import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_research_contract_command_writes_contract_only(tmp_path: Path, capsys):
    out = tmp_path / "research"

    code = main(
        [
            "research-contract",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    archetype = json.loads((out / "archetype_research.json").read_text(encoding="utf-8"))
    card_roles = json.loads((out / "card_role_map.json").read_text(encoding="utf-8"))
    globalvalue_intent = json.loads((out / "globalvalue_intent.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["research_dir"] == str(out)
    assert archetype["deck_name"] == "ShadowPriest"
    assert card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in card_roles["SW_448"]["roles"]
    assert globalvalue_intent["overlays"]["MyHeroPowerValue"] == "increase"
    assert not (out / "CustomConfig").exists()
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_prepare_cli.py::test_research_contract_command_writes_contract_only -q
```

Expected: FAIL with `Unknown command: research-contract`.

- [ ] **Step 3: Add parser entries**

In `_build_parser()` in `src/hsconfig/cli.py`, add:

```python
    research_contract = subparsers.add_parser("research-contract")
    research_contract.add_argument("--deck-name", required=True)
    research_contract.add_argument("--deck-code", required=True)
    research_contract.add_argument("--out", required=True)
    research_contract.add_argument("--cards-json")
    research_contract.add_argument("--claims-json")
    research_contract.add_argument("--allow-placeholder", action="store_true")
    research_contract.add_argument("--json", action="store_true")
```

In `main()`, add a dispatch branch before `validate`:

```python
        elif args.command == "research-contract":
            payload, code = _research_contract(args)
```

- [ ] **Step 4: Add the command implementation**

In `src/hsconfig/cli.py`, add this function below `_build`:

```python
def _research_contract(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)

    cards_payload = _load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    cards = cards_payload["cards"]
    claims = _load_claims(args.claims_json)
    source_records = _source_records_from_cards(cards)
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards,
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
    )
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
    normalized_claims = normalize_source_claims(claims)
    bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": semantic_report["cards"]},
        source_claims=normalized_claims,
    )
    write_research_contract_bundle_to_dir(bundle, out)

    return (
        {
            "status": "passed",
            "research_dir": str(out),
            "deck_slug": deck_identity["deck_slug"],
            "confidence": bundle["archetype_research"]["confidence"],
        },
        0,
    )
```

Keep this implementation intentionally duplicated from `_build` for this task. Task 6 removes the duplication after the command behavior is locked by tests. Write directly to the requested output directory; do not write to and move from a sibling `research` directory.

- [ ] **Step 5: Run focused command test**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_prepare_cli.py::test_research_contract_command_writes_contract_only -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_prepare_cli.py
git commit -m "feat: add research contract command"
```

---

### Task 5: Add `prepare` as the Normal One-Shot Command

**Files:**

- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_prepare_cli.py`
- Modify: `tests/test_shadowpriest_e2e.py`

- [ ] **Step 1: Add failing prepare CLI test**

Append this test to `tests/test_prepare_cli.py`:

```python
def test_prepare_builds_valid_package_with_research_artifacts(tmp_path: Path, capsys):
    package = tmp_path / "shadowpriest_package"
    runtime = tmp_path / "runtime"

    code = main(
        [
            "prepare",
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

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    research_dir = reports / "research"
    validation = json.loads((reports / "validation_report.json").read_text(encoding="utf-8"))
    card_roles = json.loads((research_dir / "card_role_map.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["command"] == "prepare"
    assert payload["package"] == str(package)
    assert validation["status"] == "passed"
    assert (package / "CustomConfig" / "shadowpriest" / "GlobalValues.json").exists()
    assert (package / "CustomConfig" / "shadowpriest" / "Mulligan.json").exists()
    assert card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_prepare_cli.py::test_prepare_builds_valid_package_with_research_artifacts -q
```

Expected: FAIL with `Unknown command: prepare`.

- [ ] **Step 3: Add parser and dispatch**

In `_build_parser()`, add:

```python
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--deck-name", required=True)
    prepare.add_argument("--deck-code", required=True)
    prepare.add_argument("--out", required=True)
    prepare.add_argument("--runtime-root", required=True)
    prepare.add_argument("--cards-json")
    prepare.add_argument("--claims-json")
    prepare.add_argument("--allow-placeholder", action="store_true")
    prepare.add_argument("--json", action="store_true")
```

In `main()`, add a dispatch branch before `build`:

```python
        if args.command == "prepare":
            payload, code = _prepare(args)
        elif args.command == "build":
            payload, code = _build(args)
```

- [ ] **Step 4: Implement `_prepare` as a wrapper around `_build`**

Add this function above `_build`:

```python
def _prepare(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload, code = _build(args)
    payload = dict(payload)
    payload["command"] = "prepare"
    if code == 0:
        payload["next_action"] = "READY_TO_APPLY_OR_HANDOFF"
    return payload, code
```

This keeps `prepare` thin: it uses the same compiler pipeline as `build`, but it becomes the operator-facing command for a full deck-to-validated-package pass.

- [ ] **Step 5: Extend ShadowPriest E2E to use `prepare`**

In `tests/test_shadowpriest_e2e.py`, change the command name in the first `main([...])` call from:

```python
            "build",
```

to:

```python
            "prepare",
```

After reading `semantic_audit`, add:

```python
    research_dir = reports / "research"
    research_card_roles = json.loads(
        (research_dir / "card_role_map.json").read_text(encoding="utf-8")
    )
    research_globalvalues = json.loads(
        (research_dir / "globalvalue_intent.json").read_text(encoding="utf-8")
    )
```

Add these assertions before the runtime apply assertions:

```python
    assert research_card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in research_card_roles["SW_448"]["roles"]
    assert research_globalvalues["overlays"]["MyHeroPowerValue"] == "increase"
```

- [ ] **Step 6: Run prepare tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_prepare_cli.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_prepare_cli.py tests/test_shadowpriest_e2e.py
git commit -m "feat: add prepare command for deck to config"
```

---

### Task 6: Refactor CLI Pipeline Without Changing Behavior

**Files:**

- Modify: `src/hsconfig/cli.py`
- Test: `tests/test_prepare_cli.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_shadowpriest_e2e.py`

- [ ] **Step 1: Add a regression test that build and research-contract agree on research confidence**

Append this test to `tests/test_prepare_cli.py`:

```python
def test_build_and_research_contract_agree_on_shadowpriest_research(tmp_path: Path, capsys):
    research_out = tmp_path / "research_only"
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    assert (
        main(
            [
                "research-contract",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--out",
                str(research_out),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
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
        == 0
    )
    capsys.readouterr()

    research_only = json.loads((research_out / "archetype_research.json").read_text(encoding="utf-8"))
    build_research = json.loads(
        (package / "reports" / "research" / "archetype_research.json").read_text(
            encoding="utf-8"
        )
    )

    assert build_research["confidence"] == research_only["confidence"]
    assert build_research["deck_name"] == research_only["deck_name"]
```

- [ ] **Step 2: Run the regression test**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_prepare_cli.py::test_build_and_research_contract_agree_on_shadowpriest_research -q
```

Expected: PASS before the refactor.

- [ ] **Step 3: Extract shared pre-build context**

In `src/hsconfig/cli.py`, add this helper above `_prepare`:

```python
def _build_preconfig_context(args: argparse.Namespace) -> dict[str, Any]:
    cards_payload = _load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    cards = cards_payload["cards"]
    claims = _load_claims(args.claims_json)
    source_records = _source_records_from_cards(cards)
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards,
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
    )
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
    source_claims = normalize_source_claims(claims)
    enriched_card_metadata = {"cards": semantic_report["cards"]}
    research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=enriched_card_metadata,
        source_claims=source_claims,
    )
    return {
        "cards_payload": cards_payload,
        "deck_identity": deck_identity,
        "card_metadata": enriched_card_metadata,
        "semantic_report": semantic_report,
        "source_claims": source_claims,
        "research_bundle": research_bundle,
    }
```

- [ ] **Step 4: Replace duplicate setup in `_build` and `_research_contract`**

In `_build`, replace the duplicated card/deck/semantic/research setup with:

```python
    context = _build_preconfig_context(args)
    cards_payload = context["cards_payload"]
    deck_identity = context["deck_identity"]
    card_metadata = context["card_metadata"]
    semantic_report = context["semantic_report"]
    source_claims = context["source_claims"]
    research_bundle = context["research_bundle"]
```

In `_research_contract`, replace duplicated setup with:

```python
    context = _build_preconfig_context(args)
    deck_identity = context["deck_identity"]
    bundle = context["research_bundle"]
```

Keep the existing write behavior in each command.

- [ ] **Step 5: Run CLI regression tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_prepare_cli.py tests/test_cli.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/cli.py tests/test_prepare_cli.py
git commit -m "refactor: share hsconfig prebuild context"
```

---

### Task 7: Preserve Research Confidence in Gameplan Contract

**Files:**

- Modify: `src/hsconfig/gameplan_contract.py`
- Modify: `tests/test_gameplan_contract.py`

- [ ] **Step 1: Add failing test for guide-backed confidence lane**

Append this test to `tests/test_gameplan_contract.py`:

```python
def test_gameplan_contract_preserves_guide_backed_confidence_lane():
    deck_identity = {
        "deck_name": "Fixture Aggro",
        "cards": [{"card_id": "EX1_001", "count": 2}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_001", "name": "One", "mechanic_families": []}]}
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "claim": "Always keep One and push face damage early.",
                "cards": ["EX1_001"],
                "claim_type": "mulligan_and_gameplan",
                "confidence": "guide_backed",
            }
        ]
    )

    contract = build_gameplan_contract(deck_identity, card_metadata, source_claims)

    assert contract["cards"]["EX1_001"]["coverage_status"] == "guide_backed"
    assert contract["cards"]["EX1_001"]["confidence"] == "guide_backed"
    assert contract["mulligan_anchors"][0]["confidence"] == "guide_backed"
```

- [ ] **Step 2: Run the failing test**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_gameplan_contract.py::test_gameplan_contract_preserves_guide_backed_confidence_lane -q
```

Expected: FAIL because current coverage uses `source_backed`.

- [ ] **Step 3: Update confidence inference**

In `src/hsconfig/gameplan_contract.py`, replace:

```python
        coverage_status = "source_backed" if related_claims else "generic_low_confidence"
```

with:

```python
        coverage_status = _coverage_status(related_claims, semantic_families)
```

Add this helper near `_confidence_label`:

```python
def _coverage_status(claims: list[dict[str, Any]], semantic_families: list[str]) -> str:
    if claims:
        if any(_is_guide_claim(claim) for claim in claims):
            return "guide_backed"
        return "source_backed"
    if {"hero_power_transform", "hero_power_pressure", "start_of_game", "shadowform"} & set(
        semantic_families
    ):
        return "source_backed_static_semantics"
    if semantic_families:
        return "archetype_inferred"
    return "generic_low_confidence"


def _is_guide_claim(claim: dict[str, Any]) -> bool:
    if str(claim.get("confidence")) == "guide_backed":
        return True
    source = str(claim.get("source", "")).lower()
    url = str(claim.get("url", "")).lower()
    source_title = str(claim.get("source_title", "")).lower()
    return "guide" in source or "guide" in url or "guide" in source_title
```

Replace `_confidence_label` with:

```python
def _confidence_label(card_map: dict[str, dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    if not claims:
        statuses = {card["coverage_status"] for card in card_map.values()}
        if statuses == {"generic_low_confidence"}:
            return "generic_low_confidence"
        if "source_backed_static_semantics" in statuses:
            return "source_backed_static_semantics"
        if "archetype_inferred" in statuses:
            return "archetype_inferred"
        return "generic_low_confidence"
    statuses = {card["coverage_status"] for card in card_map.values()}
    if statuses == {"guide_backed"}:
        return "guide_backed"
    if statuses <= {"source_backed", "guide_backed"}:
        return "source_backed"
    return "mixed"
```

- [ ] **Step 4: Update existing test expectation**

In `test_gameplan_contract_covers_every_card_with_source_confidence`, change:

```python
    assert contract["confidence_label"] == "source_backed"
```

to:

```python
    assert contract["confidence_label"] == "guide_backed"
```

Guide-like sources without an explicit confidence field are intentionally promoted to `guide_backed`.

In `test_gameplan_contract_turns_shadowform_semantics_into_hero_power_pressure`, add:

```python
    assert darkbishop["confidence"] == "source_backed_static_semantics"
```

- [ ] **Step 5: Run gameplan tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_gameplan_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Run focused integration tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_research_contract.py tests/test_prepare_cli.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/gameplan_contract.py tests/test_gameplan_contract.py
git commit -m "feat: preserve research confidence lanes"
```

---

### Task 8: Update Docs And Skill Normal Path

**Files:**

- Modify: `README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `tests/test_skill_files.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing docs tests**

In `tests/test_skill_files.py`, update `test_skill_content_sets_direct_config_boundary` by adding:

```python
    assert "hsconfig prepare" in text
    assert "research contract" in text.lower()
```

In `test_skill_workflow_documents_deckstring_default_and_runtime_mapping`, add:

```python
    assert "hsconfig prepare" in text
    assert "research-contract" in text
    assert "reports/research" in text
```

In `tests/test_cli.py`, add this test:

```python
def test_readme_documents_prepare_as_normal_path():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "hsconfig prepare" in text
    assert "reports/research" in text
    assert "hsconfig build" in text
    assert "hsconfig apply" in text
```

- [ ] **Step 2: Run docs tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_skill_files.py tests/test_cli.py::test_readme_documents_prepare_as_normal_path -q
```

Expected: FAIL because `prepare` is not yet documented.

- [ ] **Step 3: Update `README.md` command section**

Replace the first command subsection under `## Commands` with:

```markdown
Prepare a complete validated package from deck input. This is the normal path.
`prepare` decodes the deck code through HearthSim deckstrings, enriches card
semantics, writes the research contract under `reports/research/`, compiles
the runtime config, and validates the package.

```powershell
hsconfig prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\outputs\shadowpriest" --json
```

Diagnostic research-only output:

```powershell
hsconfig research-contract --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --out ".\outputs\shadowpriest\reports\research" --json
```

Lower-level package build remains available when a caller already controls
the research inputs:
```

Keep the existing `hsconfig build`, `validate`, and `apply` examples after this block.

- [ ] **Step 4: Update skill files**

In `.agents/skills/hsconfig/SKILL.md`, replace the workflow list with:

```markdown
Workflow:

1. Use `hsconfig prepare` as the normal deck-to-config path.
2. Decode the deck code first and record exact CardIDs in `deckstring_decode_receipt.json` and `card_id_map.json`.
3. Write the research contract under `reports/research/`: archetype, claims, card roles, mulligan anchors, usage expectations, bad patterns, and GlobalValues intent.
4. Generate direct runtime config surfaces only: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` when a concrete valid combo exists.
5. Validate the package before any apply.
6. Runtime apply only when the user asks; apply updates `CustomConfig/deck_config.ini` for the visible HearthRanger deck name.
```

In `.agents/skills/hsconfig/references/workflow.md`, replace the content with:

```markdown
# Workflow

Normal flow: deck input -> `hsconfig prepare` -> HearthSim deckstring decode -> exact identity -> card metadata -> guide/static research contract -> guide-backed gameplan -> surface intent -> compilers -> validation -> optional runtime apply.

Use `hsconfig prepare` for package creation. It writes `deckstring_decode_receipt.json`, `card_id_map.json`, `gameplan_contract.json`, `surface_intent.json`, validation reports, and `reports/research/*`.

Use `hsconfig research-contract` only when the research bundle should be inspected before compiling config files. It writes no `CustomConfig` runtime package.

Use `hsconfig build` as a lower-level command when a caller already controls explicit `--cards-json` or `--claims-json` inputs. It still writes `reports/research/*`.

Use `hsconfig validate` before handoff or apply. Use `hsconfig apply` only when the user explicitly asks to write to a HearthRanger runtime; apply copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder.
```

In `.agents/skills/hsconfig/references/guide-research-policy.md`, replace the content with:

```markdown
# Guide Research Policy

Use current deck guides and data sources as strategic priors when live research is part of the request.

Every claim must record source, URL or source name, affected cards, claim type, confidence, and whether it became runtime config intent or remained only explanatory.

Confidence lanes:

- `guide_backed`: current deck guide or explicit supplied claim supports the card expectation.
- `source_backed_static_semantics`: card text or HearthstoneJSON semantics prove the behavior without a deck guide.
- `archetype_inferred`: mechanics imply a reasonable deck-plan role, but no direct guide claim exists.
- `generic_low_confidence`: HSConfig can only cover the card generically.

The research contract lives under `reports/research/` and includes archetype, claims, card roles, mulligan anchors, usage expectations, known bad patterns, and GlobalValues intent.

Do not infer replay performance, winrate, or postgame tuning from HSConfig outputs.
```

- [ ] **Step 5: Run docs tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_skill_files.py tests/test_cli.py::test_readme_documents_prepare_as_normal_path -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/guide-research-policy.md tests/test_skill_files.py tests/test_cli.py
git commit -m "docs: make prepare the hsconfig normal path"
```

---

### Task 9: Final Verification And GitHub Update

**Files:**

- Read: all changed files
- Modify: none unless verification exposes a defect

- [ ] **Step 1: Run targeted tests**

Run:

```powershell
$env:PYTHONPATH='src'; pytest tests/test_research_contract.py tests/test_prepare_cli.py tests/test_cli.py tests/test_gameplan_contract.py tests/test_shadowpriest_e2e.py tests/test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full suite**

Run:

```powershell
$env:PYTHONPATH='src'; pytest -q
```

Expected: PASS.

- [ ] **Step 3: Run a local ShadowPriest prepare smoke test**

Run:

```powershell
Remove-Item -LiteralPath '.\tmp\plan-shadowpriest' -Recurse -Force -ErrorAction SilentlyContinue
$env:PYTHONPATH='src'; python -m hsconfig.cli prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out ".\tmp\plan-shadowpriest" --json
$env:PYTHONPATH='src'; python -m hsconfig.cli validate --package ".\tmp\plan-shadowpriest" --json
```

Expected: both commands return JSON with `"status": "passed"`.

- [ ] **Step 4: Inspect generated research reports**

Run:

```powershell
$json = Get-Content -LiteralPath '.\tmp\plan-shadowpriest\reports\research\card_role_map.json' -Raw | ConvertFrom-Json
$json.SW_448.roles
Get-Content -LiteralPath '.\tmp\plan-shadowpriest\reports\research\globalvalue_intent.json' -Raw
```

Expected:

- `SW_448.roles` includes `hero_power_transform` and `hero_power_pressure`.
- `globalvalue_intent.json` includes `"MyHeroPowerValue": "increase"`.

- [ ] **Step 5: Remove temporary smoke output**

Run:

```powershell
Remove-Item -LiteralPath '.\tmp\plan-shadowpriest' -Recurse -Force -ErrorAction SilentlyContinue
```

Expected: `. \tmp\plan-shadowpriest` no longer exists.

- [ ] **Step 6: Review diff**

Run:

```powershell
git status --short --branch
git diff --stat
git diff -- README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md .agents/skills/hsconfig/references/guide-research-policy.md
git diff -- src/hsconfig/cli.py src/hsconfig/research_contract.py src/hsconfig/gameplan_contract.py
```

Expected:

- Only HSConfig source, tests, README, and skill docs changed.
- No `outputs/`, runtime configs, logs, or temporary smoke artifacts are staged.

- [ ] **Step 7: Commit any final fixup changes**

If verification required edits after Task 8, commit them:

```powershell
git add <changed-source-test-doc-files>
git commit -m "fix: stabilize hsconfig research prepare flow"
```

If no fixups were needed, do not create an empty commit.

- [ ] **Step 8: Push `main`**

Run:

```powershell
git push origin main
```

Expected: push succeeds and `main` is current on GitHub.

---

## Self-Review

**Spec coverage:**

- Research contract before config build: Task 1, Task 2, Task 3, Task 4, Task 5.
- Deck-neutral and ShadowPriest-proven: Task 1 fixture deck, Task 4 and Task 5 ShadowPriest, Task 9 smoke.
- Existing build compatibility: Task 3 and Task 6 preserve `build`.
- Normal one-shot operator command: Task 5 and Task 8 document `prepare`.
- Guide/static confidence lanes: Task 1, Task 2, Task 7, Task 8.
- No HSTuner scope creep: file structure and Task 8 explicitly exclude replay, winrate, logs, sessions, and candidate promotion.
- Full GlobalValues intent link: Task 1, Task 2, Task 4, Task 9 verify `MyHeroPowerValue`.
- Skill and README clarity: Task 8.

**Placeholder scan:**

- No placeholder markers, deferred-implementation markers, or undefined command names remain.
- Each code-changing task includes the exact intended test code, implementation snippets, commands, and expected results.

**Type consistency:**

- `build_research_contract_bundle(deck_identity, card_metadata, source_claims)` is used consistently by tests and CLI.
- `write_research_contract_bundle(bundle, reports_dir)` writes to `reports_dir / "research"`, and `research-contract` moves that folder to the requested contract-only output path.
- Confidence lanes are consistently named: `guide_backed`, `source_backed`, `source_backed_static_semantics`, `archetype_inferred`, `generic_low_confidence`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-05-hsconfig-research-contract-builder.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.

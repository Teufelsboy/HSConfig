# Contract Spine Slimness And Semantic Qualifiers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep HSConfig's current source-contract spine, remove duplicated authority, and add typed Hearthstone semantic qualifiers so every valid deck still produces a load-safe package without false runtime claims.

**Architecture:** Preserve the single normal apply authority: `reports/operator_summary.json`. Source claims continue through `claim_kind` -> `source_contract_matrix` -> surface gate -> builder/router -> runtime files. Improvements are narrow: one shared preconfig context, one guide-claim bundle authority, structured semantic qualifiers on existing claim kinds, stronger suspicious mulligan suppression, broader diagnostic conflict reports, and documentation/tests proving diagnostics never become apply gates.

**Tech Stack:** Python 3, stdlib typing/dataclasses, pytest, existing HSConfig modules under `src/hsconfig`, no new runtime dependencies.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not create a new pipeline or second apply authority.
- `reports/operator_summary.json` remains the only normal runtime-write/apply authority.
- `Presume.json` and `Concede.json` remain legacy/diagnostic surfaces outside the normal package output path.
- Unsupported or thin-source mechanics must stay warning/report visible, not package blockers.
- Runtime lowering may use only documented normal HSConfig surfaces: `GlobalValues.json`, `Mulligan.json`, gated per-card `<CARDID>.json`, and gated `Combo.json`.
- Preserve the Darkbishop Benedictus boundary: `hero_power_transform` / Mind Spike effect may remain in card behavior config, but the card is not an opening-hand keep unless source text explicitly says mulligan/opening hand.
- Keep changes subtractive and targeted; no broad rewrites, no new dependencies.
- Research baseline: `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v5/` validated 6/6 with 100% coverage.

---

## File Structure

Create:

- `src/hsconfig/preconfig_context.py`  
  Single source of truth for deck/card/source/context derivation currently duplicated between `source_workflow.py` and `package_builder.py`.

- `src/hsconfig/source_semantic_qualifiers.py`  
  Normalizes typed semantic qualifiers carried by existing claims. Does not define new top-level claim kinds.

- `src/hsconfig/source_claim_conflicts.py`  
  Builds broader diagnostic conflicts for mulligan, targeting, combo, option choice, and role-vs-bad-pattern contradictions.

- `tests/test_preconfig_context_parity.py`  
  Proves `research-deck` and `prepare` use the shared context and produce matching source facts.

- `tests/test_semantic_qualifiers.py`  
  Proves qualifiers are normalized, preserved, and used without widening runtime authority.

- `tests/test_source_claim_conflicts.py`  
  Proves broader conflict families are visible but non-blocking.

Modify:

- `src/hsconfig/commands/source_workflow.py`  
  Replace `_build_research_context()` with import/delegation to `preconfig_context.build_preconfig_context()`.

- `src/hsconfig/package_builder.py`  
  Remove local `build_preconfig_context()` implementation; import the shared builder.

- `src/hsconfig/source_document_builder.py`  
  Attach semantic qualifiers during source claim normalization and use `source_claim_conflicts.build_claim_conflict_report()`.

- `src/hsconfig/guide_claim_builder.py`  
  Attach safe static semantic qualifiers to static claims.

- `src/hsconfig/source_document_model.py`  
  Use semantic qualifiers in mulligan suppression without changing the existing surface-gate contract.

- `src/hsconfig/source_evidence_verifier.py`  
  Treat semantic qualifier fields as actionable specificity and warn on suspicious exact keeps even if role enrichment is incomplete.

- `src/hsconfig/source_contract_matrix.py`  
  Add required/optional qualifier metadata to existing policy rows; do not add new claim kinds unless an existing test proves impossible otherwise.

- `src/hsconfig/surface_intent.py`  
  Clarify minimum required runtime surfaces vs rich optional per-card surfaces in the report payload.

- `src/hsconfig/report_ownership.py` and `src/hsconfig/output_ownership_manifest.py`  
  Keep artifact ownership coherent if any new diagnostic report fields/files are added.

- `docs/operator/guide-research-policy.md`  
  Document source claim qualifiers, no-block semantics, and non-apply diagnostic boundaries.

- `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md`  
  Keep the skill aligned with the active operator contract.

---

### Task 1: Shared Preconfig Context Authority

**Files:**
- Create: `src/hsconfig/preconfig_context.py`
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/package_builder.py`
- Test: `tests/test_preconfig_context_parity.py`

**Interfaces:**
- Produces: `build_preconfig_context(args: argparse.Namespace) -> dict[str, Any]`
- Produces context keys used by existing callers: `cards_payload`, `deck_identity`, `card_metadata`, `semantic_report`, `guide_claim_bundle`, `source_claims`, `research_bundle`, `guide_sources_generated`, `guide_builder_receipt`, `deck_fingerprint`, `candidate_archetypes`, `identity_graph_report`, `identity_gap_report`, `source_evidence_report`, `source_document_draft_report`
- Additional key required by `research-deck`: `card_data_intake_report`
- Consumed by: `source_workflow.research_deck_payload`, `package_builder.build_package_payload`, `package_builder.research_contract_payload`

- [ ] **Step 1: Write failing parity tests**

Create `tests/test_preconfig_context_parity.py`:

```python
import argparse
import inspect

from hsconfig import package_builder
from hsconfig.commands import source_workflow
from hsconfig.preconfig_context import build_preconfig_context


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _args(tmp_path):
    return argparse.Namespace(
        deck_name="ShadowPriest",
        deck_code=SHADOWPRIEST_CODE,
        out=str(tmp_path / "out"),
        runtime_root=str(tmp_path / "runtime"),
        cards_json=None,
        claims_json=None,
        guide_sources_json=None,
        source_documents_json=None,
        source_evidence_json=None,
        collectible_cards_json=None,
        full_cards_json=None,
        allow_placeholder=False,
        auto_research_fallback=True,
        skip_semantic_fetch=True,
        plan_reports_dir=None,
    )


def test_shared_preconfig_context_contains_prepare_and_research_keys(tmp_path):
    context = build_preconfig_context(_args(tmp_path))

    expected = {
        "cards_payload",
        "deck_identity",
        "card_metadata",
        "semantic_report",
        "guide_claim_bundle",
        "source_claims",
        "research_bundle",
        "guide_sources_generated",
        "guide_builder_receipt",
        "deck_fingerprint",
        "candidate_archetypes",
        "identity_graph_report",
        "identity_gap_report",
        "source_evidence_report",
        "source_document_draft_report",
        "card_data_intake_report",
    }
    assert expected <= set(context)
    assert context["deck_identity"]["deck_name"] == "ShadowPriest"
    assert context["guide_claim_bundle"]["claims"]


def test_research_and_prepare_no_longer_own_duplicate_context_builders():
    source = inspect.getsource(source_workflow)
    package = inspect.getsource(package_builder)

    assert "def _build_research_context(" not in source
    assert "def build_preconfig_context(" not in package
    assert "from hsconfig.preconfig_context import build_preconfig_context" in source
    assert "from hsconfig.preconfig_context import build_preconfig_context" in package
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_preconfig_context_parity.py -q
```

Expected before implementation: FAIL because `hsconfig.preconfig_context` does not exist or duplicate builders still exist.

- [ ] **Step 3: Extract shared implementation**

Create `src/hsconfig/preconfig_context.py` by moving the current `package_builder.build_preconfig_context()` implementation into the new module. While moving, add the `card_data_intake_report` logic currently present only in `source_workflow._build_research_context()`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.card_feed_loading import (
    card_feed_receipt_source,
    card_feed_receipt_status,
    load_optional_card_feed,
)
from hsconfig.card_data_intake import build_card_data_context
from hsconfig.card_metadata import hydrate_card_metadata
from hsconfig.deck_identity import build_deck_identity
from hsconfig.guide_claim_builder import build_guide_claim_bundle
from hsconfig.guide_source_builder import (
    build_candidate_archetypes,
    build_deck_fingerprint,
    build_guide_builder_receipt,
    build_guide_sources,
    research_required_guide_sources,
)
from hsconfig.hearthstonejson import fetch_latest_cards, fetch_latest_collectible_cards
from hsconfig.identity_graph import build_identity_gap_report, build_identity_graph_report
from hsconfig.input_loading import (
    guide_documents_from_legacy_claims,
    load_cards,
    load_claims,
    load_guide_sources,
    load_source_documents,
    load_source_evidence,
    source_records_from_cards,
)
from hsconfig.research_contract import build_research_contract_bundle
from hsconfig.semantic_enrichment import append_semantic_warning, enrich_card_metadata
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_verifier import verify_source_documents


def build_preconfig_context(args: argparse.Namespace) -> dict[str, Any]:
    """Build the shared deck/source context used by research and prepare commands."""
    # Move the existing body from package_builder.build_preconfig_context here.
    # Preserve current return keys and add card_data_intake_report.
```

Do not leave a second implementation in `package_builder.py`. The final function body should be the moved existing logic, not a rewrite.

- [ ] **Step 4: Wire both callers**

In `src/hsconfig/package_builder.py`, remove the local function and import:

```python
from hsconfig.preconfig_context import build_preconfig_context
```

In `src/hsconfig/commands/source_workflow.py`, remove `_build_research_context()` and import:

```python
from hsconfig.preconfig_context import build_preconfig_context
```

Then change:

```python
context = _build_research_context(args)
```

to:

```python
context = build_preconfig_context(args)
```

- [ ] **Step 5: Run focused tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_preconfig_context_parity.py tests/test_autonomous_guide_workflow_e2e.py tests/test_prepare_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/preconfig_context.py src/hsconfig/commands/source_workflow.py src/hsconfig/package_builder.py tests/test_preconfig_context_parity.py
git commit -m "refactor: share preconfig context authority"
```

---

### Task 2: Guide Claim Bundle Parity Sentinel

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/research_contract.py`
- Test: `tests/test_guide_claim_bundle_parity.py`

**Interfaces:**
- Produces: `guide_claim_bundle` emitted once as canonical package authority at `reports/guide_claim_bundle.json`
- Produces optional research copy only if byte-for-byte equal or replaced by pointer metadata

- [ ] **Step 1: Write failing parity test**

Create `tests/test_guide_claim_bundle_parity.py`:

```python
import json

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_package_has_single_canonical_guide_claim_bundle_or_identical_copy(tmp_path):
    out = tmp_path / "pkg"
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
            "--skip-semantic-fetch",
        ]
    )

    assert code == 0
    canonical_path = out / "reports" / "guide_claim_bundle.json"
    duplicate_path = out / "reports" / "research" / "guide_claim_bundle.json"
    assert canonical_path.exists()
    if duplicate_path.exists():
        canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
        duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
        assert duplicate == canonical
```

- [ ] **Step 2: Run test to establish current behavior**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_guide_claim_bundle_parity.py -q
```

Expected: PASS if already identical, FAIL if duplicate drift exists. If PASS, keep the test as a sentinel.

- [ ] **Step 3: Remove or normalize duplicate emission**

If `reports/research/guide_claim_bundle.json` is not needed by active tests, update `write_research_contract_bundle()` so it writes a pointer row instead of a duplicate:

```json
{
  "schema_version": 1,
  "canonical_report": "../guide_claim_bundle.json",
  "authority": "reports/guide_claim_bundle.json"
}
```

If active tests require the duplicate, keep it but ensure it receives the exact same `guide_claim_bundle` object from the shared preconfig context and add the parity test.

- [ ] **Step 4: Run targeted tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_guide_claim_bundle_parity.py tests/test_report_ownership.py tests/test_output_ownership_manifest.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/package_builder.py src/hsconfig/research_contract.py tests/test_guide_claim_bundle_parity.py
git commit -m "test: guard guide claim bundle parity"
```

---

### Task 3: Semantic Qualifier Model On Existing Claims

**Files:**
- Create: `src/hsconfig/source_semantic_qualifiers.py`
- Modify: `src/hsconfig/source_document_builder.py`
- Modify: `src/hsconfig/guide_claim_builder.py`
- Modify: `src/hsconfig/source_evidence_verifier.py`
- Test: `tests/test_semantic_qualifiers.py`

**Interfaces:**
- Produces: `normalize_semantic_qualifiers(claim: Mapping[str, Any], *, card_roles: Mapping[str, Any] | None = None) -> dict[str, Any]`
- Produces claim field: `semantic_qualifiers: dict[str, Any]`
- The qualifiers are explanatory and gate-supporting metadata; they do not create a new runtime surface.

- [ ] **Step 1: Write failing qualifier tests**

Create `tests/test_semantic_qualifiers.py`:

```python
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_semantic_qualifiers import normalize_semantic_qualifiers
from hsconfig.source_evidence_verifier import claim_evidence_status


def test_normalize_semantic_qualifiers_keeps_known_fields_and_drops_empty_values():
    result = normalize_semantic_qualifiers(
        {
            "timing": "Start of Game",
            "zone_scope": "Deck",
            "target_scope": "",
            "option_surface": "Discover",
            "state_requirements": ["all_shadow_spells", ""],
        }
    )

    assert result == {
        "timing": "start_of_game",
        "zone_scope": "deck",
        "option_surface": "discover",
        "state_requirements": ["all_shadow_spells"],
    }


def test_source_document_claim_preserves_semantic_qualifiers():
    bundle = build_source_document_bundle(
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus"}],
        },
        card_metadata={
            "SW_448": {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "text": "Start of Game: Enter Shadowform.",
            }
        },
        source_documents=[
            {
                "source_url": "https://example.com/shadowpriest",
                "source_title": "ShadowPriest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-13",
                "claims": [
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "evidence_text_short": "Start of Game changes Hero Power.",
                        "source_confidence": "high",
                        "timing": "start_of_game",
                        "zone_scope": "deck",
                        "state_requirements": ["all_shadow_spells"],
                    }
                ],
            }
        ],
    )

    claim = bundle["claims"][0]
    assert claim["semantic_qualifiers"] == {
        "timing": "start_of_game",
        "zone_scope": "deck",
        "state_requirements": ["all_shadow_spells"],
    }


def test_semantic_qualifiers_count_as_actionable_specificity_for_runtime_hints():
    row = claim_evidence_status(
        {
            "claim_kind": "targeting_rule",
            "cards": ["CARD_001"],
            "evidence_text_short": "Send burn face.",
            "source_confidence": "high",
            "runtime_block": "BeforeBattlecryTargetBonus",
            "semantic_qualifiers": {"target_scope": "enemy_hero"},
        },
        {"source_family": "guide", "source_url": "https://example.com"},
    )

    assert not any(
        warning["reason"] == "runtime_lowering_claim_lacks_actionable_specificity"
        for warning in row["warnings"]
    )
```

- [ ] **Step 2: Run failing tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_qualifiers.py -q
```

Expected: FAIL because `source_semantic_qualifiers.py` does not exist.

- [ ] **Step 3: Create qualifier normalizer**

Create `src/hsconfig/source_semantic_qualifiers.py`:

```python
from __future__ import annotations

from typing import Any, Mapping


QUALIFIER_KEYS = (
    "timing",
    "zone_scope",
    "target_scope",
    "option_surface",
    "state_requirements",
)

ALIASES = {
    "start of game": "start_of_game",
    "opening hand": "mulligan",
    "starting hand": "mulligan",
    "in deck": "deck",
    "deck": "deck",
    "hand": "hand",
    "board": "board",
    "enemy hero": "enemy_hero",
    "enemy face": "enemy_hero",
    "friendly minion": "friendly_minion",
    "enemy minion": "enemy_minion",
    "discover": "discover",
    "choose one": "choose_one",
}


def normalize_semantic_qualifiers(
    claim: Mapping[str, Any],
    *,
    card_roles: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    raw = claim.get("semantic_qualifiers", {})
    if isinstance(raw, Mapping):
        for key in QUALIFIER_KEYS:
            _add_value(result, key, raw.get(key))
    for key in QUALIFIER_KEYS:
        _add_value(result, key, claim.get(key))

    roles = _role_tokens(claim, card_roles or {})
    if "start_of_game" in roles:
        result.setdefault("timing", "start_of_game")
    if "hero_power_transform" in roles:
        result.setdefault("state_requirements", [])
        if "hero_power_transform" not in result["state_requirements"]:
            result["state_requirements"].append("hero_power_transform")
    return result


def has_qualifier(claim: Mapping[str, Any], key: str, value: str) -> bool:
    qualifiers = claim.get("semantic_qualifiers", {})
    if not isinstance(qualifiers, Mapping):
        return False
    current = qualifiers.get(key)
    if isinstance(current, list):
        return value in current
    return current == value


def _add_value(result: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        normalized = _normalize_text(value)
        if normalized:
            result[key] = normalized
        return
    if isinstance(value, list):
        values = [_normalize_text(item) for item in value]
        values = [item for item in values if item]
        if values:
            result[key] = list(dict.fromkeys(values))
        return


def _normalize_text(value: Any) -> str:
    text = " ".join(str(value).strip().lower().replace("-", " ").split())
    return ALIASES.get(text, text.replace(" ", "_"))


def _role_tokens(claim: Mapping[str, Any], card_roles: Mapping[str, Any]) -> set[str]:
    roles: set[str] = set()
    for key in ("roles", "semantic_families", "mechanic_families"):
        value = claim.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            roles.update(_normalize_text(item) for item in value if str(item).strip())
    for card_id in claim.get("cards", []) if isinstance(claim.get("cards", []), list) else []:
        row = card_roles.get(str(card_id), {})
        if not isinstance(row, Mapping):
            continue
        for key in ("roles", "semantic_families", "mechanic_families"):
            value = row.get(key, [])
            if isinstance(value, str):
                value = [value]
            if isinstance(value, list):
                roles.update(_normalize_text(item) for item in value if str(item).strip())
    return roles
```

- [ ] **Step 4: Preserve qualifiers during normalization**

In `src/hsconfig/source_document_builder.py`, import:

```python
from hsconfig.source_semantic_qualifiers import normalize_semantic_qualifiers
```

After optional fields are copied in `_normalize_source_claim()`, add:

```python
semantic_qualifiers = normalize_semantic_qualifiers(claim)
if semantic_qualifiers:
    claim["semantic_qualifiers"] = semantic_qualifiers
```

In `src/hsconfig/guide_claim_builder.py`, add the same import and set qualifiers on `_static_claim()` output:

```python
semantic_qualifiers = normalize_semantic_qualifiers(claim)
if semantic_qualifiers:
    claim["semantic_qualifiers"] = semantic_qualifiers
```

- [ ] **Step 5: Treat qualifiers as specificity**

In `src/hsconfig/source_evidence_verifier.py`, add `"semantic_qualifiers"` to `ACTIONABLE_SPECIFICITY_KEYS`.

- [ ] **Step 6: Run focused tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_qualifiers.py tests/test_source_claim_quality_autonomy.py tests/test_surface_authority_split.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/source_semantic_qualifiers.py src/hsconfig/source_document_builder.py src/hsconfig/guide_claim_builder.py src/hsconfig/source_evidence_verifier.py tests/test_semantic_qualifiers.py
git commit -m "feat: add source semantic qualifiers"
```

---

### Task 4: Stronger Suspicious Mulligan Suppression

**Files:**
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/source_evidence_verifier.py`
- Test: `tests/test_semantic_qualifiers.py`
- Test: `tests/test_surface_authority_split.py`

**Interfaces:**
- Consumes: claim field `semantic_qualifiers`
- Produces: existing suppression reason `start_of_game_effect_does_not_require_opening_hand`
- Produces verifier warning reason `suspicious_mulligan_keep_non_hand_effect`

- [ ] **Step 1: Add failing tests for qualifier-only suspicious keep**

Append to `tests/test_semantic_qualifiers.py`:

```python
from hsconfig.source_document_model import can_lower_to_mulligan


def test_start_of_game_qualifier_blocks_mulligan_keep_without_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["START_EFFECT"],
        "evidence_text_short": "Core deck enabler.",
        "semantic_qualifiers": {
            "timing": "start_of_game",
            "zone_scope": "deck",
            "state_requirements": ["hero_power_transform"],
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_start_of_game_qualifier_allows_explicit_opening_hand_text():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["START_EFFECT"],
        "evidence_text_short": "Always keep START_EFFECT in your opening hand.",
        "semantic_qualifiers": {
            "timing": "start_of_game",
            "zone_scope": "deck",
            "state_requirements": ["hero_power_transform"],
        },
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is True
```

- [ ] **Step 2: Run failing tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_qualifiers.py::test_start_of_game_qualifier_blocks_mulligan_keep_without_opening_hand_text tests/test_semantic_qualifiers.py::test_start_of_game_qualifier_allows_explicit_opening_hand_text -q
```

Expected: first test FAILS before implementation.

- [ ] **Step 3: Update suppression logic**

In `src/hsconfig/source_document_model.py`, import:

```python
from hsconfig.source_semantic_qualifiers import has_qualifier
```

In `_contains_start_of_game_non_hand_effect()`, after roles are loaded and before returning `False`, add:

```python
        qualifier_start_effect = (
            has_qualifier(claim or {}, "timing", "start_of_game")
            or has_qualifier(claim or {}, "zone_scope", "deck")
            or has_qualifier(claim or {}, "state_requirements", "hero_power_transform")
            or has_qualifier(claim or {}, "state_requirements", "deckbuilding_effect")
        )
        if qualifier_start_effect and not has_explicit_opening_hand_mulligan_intent(
            claim,
            roles=roles | {"start_of_game"},
        ):
            return True
```

- [ ] **Step 4: Update verifier warning**

In `src/hsconfig/source_evidence_verifier.py`, import:

```python
from hsconfig.source_semantic_qualifiers import has_qualifier
```

In `_suspicious_exact_keep_warning()`, treat qualifier-only start effects like role-based start effects:

```python
    has_qualifier_start_effect = (
        has_qualifier(claim, "timing", "start_of_game")
        or has_qualifier(claim, "zone_scope", "deck")
        or has_qualifier(claim, "state_requirements", "hero_power_transform")
        or has_qualifier(claim, "state_requirements", "deckbuilding_effect")
    )
    if has_qualifier_start_effect:
        return {
            "reason": "suspicious_mulligan_keep_non_hand_effect",
            "claim_kind": claim_kind,
            "roles": sorted(roles),
            "semantic_qualifiers": claim.get("semantic_qualifiers", {}),
        }
```

- [ ] **Step 5: Run focused tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_semantic_qualifiers.py tests/test_surface_authority_split.py tests/test_archetype_source_fixtures.py::test_shadowpriest_fixture_does_not_mulligan_keep_darkbishop_start_of_game_effect -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_document_model.py src/hsconfig/source_evidence_verifier.py tests/test_semantic_qualifiers.py
git commit -m "fix: suppress start effect mulligan claims by qualifiers"
```

---

### Task 5: Broader Diagnostic Claim Conflict Reports

**Files:**
- Create: `src/hsconfig/source_claim_conflicts.py`
- Modify: `src/hsconfig/source_document_builder.py`
- Test: `tests/test_source_claim_conflicts.py`

**Interfaces:**
- Produces: `build_claim_conflict_report(claims: list[dict[str, Any]]) -> dict[str, Any]`
- Output shape remains compatible: `{"conflict_count": int, "conflicts": list[dict[str, Any]]}`
- Conflict reports remain diagnostic-only and must not block package generation.

- [ ] **Step 1: Write failing conflict tests**

Create `tests/test_source_claim_conflicts.py`:

```python
from hsconfig.source_claim_conflicts import build_claim_conflict_report


def _claim(claim_id, claim_kind, card, **extra):
    return {
        "claim_id": claim_id,
        "claim_kind": claim_kind,
        "cards": [card],
        "claim_readiness": "guide_backed",
        "source_confidence": "high",
        "evidence_text_short": claim_id,
        **extra,
    }


def test_conflict_report_keeps_existing_mulligan_conflict_shape():
    report = build_claim_conflict_report(
        [
            _claim("keep", "mulligan_keep", "CARD_001"),
            _claim("discard", "mulligan_discard", "CARD_001"),
        ]
    )

    assert report["conflict_count"] == 1
    conflict = report["conflicts"][0]
    assert conflict["conflict_family"] == "mulligan"
    assert conflict["card_id"] == "CARD_001"
    assert conflict["resolution"] == "downgrade_to_report_visible_conflict"


def test_conflict_report_detects_targeting_scope_conflicts():
    report = build_claim_conflict_report(
        [
            _claim(
                "face",
                "targeting_rule",
                "BURN",
                semantic_qualifiers={"target_scope": "enemy_hero"},
            ),
            _claim(
                "minion",
                "targeting_rule",
                "BURN",
                semantic_qualifiers={"target_scope": "enemy_minion"},
            ),
        ]
    )

    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["conflict_family"] == "targeting"
    assert set(report["conflicts"][0]["values"]) == {"enemy_hero", "enemy_minion"}


def test_conflict_report_detects_combo_timing_conflicts():
    report = build_claim_conflict_report(
        [
            _claim("same_turn", "combo_sequence", "A", sequence=["A", "B"], timing_kind="same_turn"),
            _claim("cross_turn", "combo_sequence", "A", sequence=["A", "B"], timing_kind="cross_turn"),
        ]
    )

    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["conflict_family"] == "combo_timing"


def test_conflict_report_detects_option_choice_conflicts():
    report = build_claim_conflict_report(
        [
            _claim("option_a", "discover_choice", "DISCOVER", option_card_id="OPTION_A"),
            _claim("option_b", "discover_choice", "DISCOVER", option_card_id="OPTION_B"),
        ]
    )

    assert report["conflict_count"] == 1
    assert report["conflicts"][0]["conflict_family"] == "option_choice"
```

- [ ] **Step 2: Run failing tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_conflicts.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement conflict module**

Create `src/hsconfig/source_claim_conflicts.py`:

```python
from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_claim_conflict_report(claims: list[dict[str, Any]]) -> dict[str, Any]:
    conflicts: list[dict[str, Any]] = []
    conflicts.extend(_mulligan_conflicts(claims))
    conflicts.extend(_targeting_conflicts(claims))
    conflicts.extend(_combo_timing_conflicts(claims))
    conflicts.extend(_option_choice_conflicts(claims))
    return {"conflict_count": len(conflicts), "conflicts": conflicts}


def _mulligan_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_card: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        kind = str(claim.get("claim_kind", ""))
        if kind not in {"mulligan_keep", "mulligan_discard"}:
            continue
        for card_id in _cards(claim):
            by_card[card_id][kind].add(str(claim.get("claim_id", "")))
    conflicts = []
    for card_id, kinds in sorted(by_card.items()):
        if {"mulligan_keep", "mulligan_discard"} <= set(kinds):
            claim_ids = sorted(set().union(*kinds.values()))
            conflicts.append(
                {
                    "card_id": card_id,
                    "conflict_family": "mulligan",
                    "claim_ids": claim_ids,
                    "resolution": "downgrade_to_report_visible_conflict",
                }
            )
    return conflicts


def _targeting_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_card: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        if str(claim.get("claim_kind", "")) != "targeting_rule":
            continue
        scope = _qualifier(claim, "target_scope") or str(claim.get("target", claim.get("stance", "")))
        if not scope:
            continue
        for card_id in _cards(claim):
            by_card[card_id][scope].add(str(claim.get("claim_id", "")))
    return _value_conflicts(by_card, "targeting")


def _combo_timing_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sequence: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        if str(claim.get("claim_kind", "")) != "combo_sequence":
            continue
        sequence = tuple(str(card) for card in claim.get("sequence", claim.get("cards", [])))
        if not sequence:
            continue
        timing = str(claim.get("timing_kind", _qualifier(claim, "timing") or ""))
        if not timing:
            continue
        by_sequence["|".join(sequence)][timing].add(str(claim.get("claim_id", "")))
    return _value_conflicts(by_sequence, "combo_timing", key_name="sequence_key")


def _option_choice_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_card: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for claim in claims:
        if str(claim.get("claim_kind", "")) not in {"discover_choice", "choose_one_choice"}:
            continue
        option = str(
            claim.get(
                "option_card_id",
                claim.get("option_card", claim.get("choice_card_id", claim.get("choice_card", ""))),
            )
        )
        if not option:
            continue
        for card_id in _cards(claim):
            by_card[card_id][option].add(str(claim.get("claim_id", "")))
    return _value_conflicts(by_card, "option_choice")


def _value_conflicts(
    grouped: dict[str, dict[str, set[str]]],
    family: str,
    *,
    key_name: str = "card_id",
) -> list[dict[str, Any]]:
    conflicts = []
    for key, values in sorted(grouped.items()):
        clean_values = {value: ids for value, ids in values.items() if value}
        if len(clean_values) <= 1:
            continue
        claim_ids = sorted(set().union(*clean_values.values()))
        conflicts.append(
            {
                key_name: key,
                "conflict_family": family,
                "values": sorted(clean_values),
                "claim_ids": claim_ids,
                "resolution": "downgrade_to_report_visible_conflict",
            }
        )
    return conflicts


def _cards(claim: dict[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _qualifier(claim: dict[str, Any], key: str) -> str:
    qualifiers = claim.get("semantic_qualifiers", {})
    if not isinstance(qualifiers, dict):
        return ""
    value = qualifiers.get(key, "")
    return str(value) if not isinstance(value, list) else "|".join(str(item) for item in value)
```

- [ ] **Step 4: Use conflict module**

In `src/hsconfig/source_document_builder.py`, import:

```python
from hsconfig.source_claim_conflicts import build_claim_conflict_report
```

Remove the local `_build_claim_conflict_report()` implementation or leave only a compatibility wrapper that calls the new module.

- [ ] **Step 5: Run focused tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_conflicts.py tests/test_source_claim_quality_autonomy.py tests/test_archetype_source_fixtures.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_claim_conflicts.py src/hsconfig/source_document_builder.py tests/test_source_claim_conflicts.py
git commit -m "feat: expand diagnostic source claim conflicts"
```

---

### Task 6: Surface Intent And Ownership Polish

**Files:**
- Modify: `src/hsconfig/surface_intent.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `src/hsconfig/output_ownership_manifest.py`
- Test: `tests/test_surface_intent.py`
- Test: `tests/test_report_ownership.py`
- Test: `tests/test_output_ownership_manifest.py`

**Interfaces:**
- Produces `surface_intent["minimum_required_runtime_surfaces"]`
- Produces `surface_intent["rich_optional_runtime_surfaces"]`
- Does not alter `operator_summary.json` apply authority.

- [ ] **Step 1: Add failing surface-intent test**

If `tests/test_surface_intent.py` exists, append; otherwise create it:

```python
from hsconfig.surface_intent import build_surface_intent


def test_surface_intent_separates_minimum_load_safe_and_rich_optional_surfaces():
    report = build_surface_intent(
        {
            "deck_name": "Intent",
            "cards": {
                "CARD_001": {"card_id": "CARD_001", "roles": ["deck_card"]},
            },
            "mulligan_plan": {"rules": []},
            "card_behavior_plan": {"rows": [{"card_id": "CARD_001"}]},
            "combo_plan": {"combos": []},
        }
    )

    assert "GlobalValues.json" in report["minimum_required_runtime_surfaces"]
    assert "Mulligan.json" in report["minimum_required_runtime_surfaces"]
    assert "CARD_001.json" in report["rich_optional_runtime_surfaces"]
    assert "Presume.json" not in report["minimum_required_runtime_surfaces"]
    assert "Concede.json" not in report["minimum_required_runtime_surfaces"]
```

- [ ] **Step 2: Run failing test**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_surface_intent.py -q
```

Expected: FAIL until fields exist.

- [ ] **Step 3: Implement report split**

Update `build_surface_intent()` to preserve existing keys and add:

```python
minimum_required_runtime_surfaces = ["GlobalValues.json", "Mulligan.json"]
rich_optional_runtime_surfaces = sorted(
    surface
    for surface in existing_runtime_surfaces
    if surface not in minimum_required_runtime_surfaces
    and surface not in {"Presume.json", "Concede.json"}
)
```

Do not add these fields to apply gate logic.

- [ ] **Step 4: Keep ownership coherent**

If the report shape changes only inside existing `surface_intent.json`, no ownership file update is needed. If a new report file is introduced, add it to both `report_ownership.py` and `output_ownership_manifest.py` as diagnostic-only.

- [ ] **Step 5: Run focused tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_surface_intent.py tests/test_report_ownership.py tests/test_output_ownership_manifest.py tests/test_apply_authority_boundary.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/surface_intent.py src/hsconfig/report_ownership.py src/hsconfig/output_ownership_manifest.py tests/test_surface_intent.py tests/test_report_ownership.py tests/test_output_ownership_manifest.py
git commit -m "docs: clarify runtime surface intent authority"
```

---

### Task 7: Contract Matrix And Docs Alignment

**Files:**
- Modify: `src/hsconfig/source_contract_matrix.py`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_source_contract_conformance.py`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_docs_active_path.py`

**Interfaces:**
- Produces policy metadata for qualifiers without adding top-level claim kinds.
- Docs state that semantic qualifiers support runtime decisions but do not bypass surface gates.

- [ ] **Step 1: Add policy metadata test**

Append to `tests/test_source_contract_conformance.py` or the nearest existing policy test:

```python
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind


def test_contract_policy_documents_semantic_qualifier_usage_without_new_gate():
    policy = source_contract_policy_by_claim_kind()

    assert policy["mulligan_keep"]["semantic_qualifier_usage"] == (
        "timing and zone qualifiers may suppress start-of-game non-hand effects"
    )
    assert policy["targeting_rule"]["semantic_qualifier_usage"] == (
        "target_scope may refine CardID targeting behavior"
    )
    assert policy["combo_sequence"]["semantic_qualifier_usage"] == (
        "timing and state requirements may refine Combo.json eligibility"
    )
    assert all(row["operator_gate_impact"] == "diagnostic_only" for row in policy.values())
```

- [ ] **Step 2: Run failing test**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_conformance.py::test_contract_policy_documents_semantic_qualifier_usage_without_new_gate -q
```

Expected: FAIL until metadata exists.

- [ ] **Step 3: Add policy metadata**

In `src/hsconfig/source_contract_matrix.py`, add `semantic_qualifier_usage` to policy rows where relevant:

```python
"semantic_qualifier_usage": "timing and zone qualifiers may suppress start-of-game non-hand effects"
```

Use exact strings from the test for `mulligan_keep`, `targeting_rule`, and `combo_sequence`. For other rows, set:

```python
"semantic_qualifier_usage": "diagnostic context only"
```

- [ ] **Step 4: Update docs**

In `docs/operator/guide-research-policy.md`, add a section:

```markdown
## Semantic Qualifiers

Semantic qualifiers refine existing source claims. They do not create a second
apply path and they do not bypass `claim_kind` or surface gates.

Supported qualifier families:

- `timing`: `mulligan`, `start_of_game`, `on_play`, `delayed`, `ongoing`, `death`, `trigger`
- `zone_scope`: `hand`, `deck`, `board`, `secret`, `location`, `generated`, `graveyard`
- `target_scope`: `enemy_hero`, `friendly_minion`, `enemy_minion`, `any_minion`, `no_target`
- `option_surface`: `discover`, `choose_one`, `generated_choice`
- `state_requirements`: deck, hand, board, weapon, mana, overload, duplicate, or mechanic constraints

When source text says an effect matters but does not explicitly say opening
hand or mulligan, HSConfig must preserve effect semantics without turning the
card into a `Mulligan.json` keep.
```

Mirror the same boundary in `.agents/skills/hsconfig/SKILL.md` and `.agents/skills/hsconfig/references/workflow.md` in shorter form.

- [ ] **Step 5: Run docs and policy tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_contract_conformance.py tests/test_skill_files.py tests/test_docs_active_path.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/source_contract_matrix.py docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/workflow.md tests/test_source_contract_conformance.py tests/test_skill_files.py tests/test_docs_active_path.py
git commit -m "docs: document semantic qualifier contract"
```

---

### Task 8: End-To-End Regression Proof

**Files:**
- Modify: `tests/test_shadowpriest_depth_e2e.py` or `tests/test_shadowpriest_e2e.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`

**Interfaces:**
- Proves the full chain remains no-block and effect-vs-mulligan safe.

- [ ] **Step 1: Add ShadowPriest effect split regression**

Append to the existing ShadowPriest E2E test file:

```python
import json

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_shadowpriest_semantic_qualifiers_preserve_effect_without_mulligan_keep(tmp_path):
    out = tmp_path / "pkg"
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
            "--skip-semantic-fetch",
        ]
    )

    assert code == 0
    reports = out / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    mulligan = json.loads(
        (out / "CustomConfig" / "ShadowPriest" / "Mulligan.json").read_text(encoding="utf-8")
    )

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert not any(
        row.get("mulligan") == "SW_448" and row.get("value") == "hold"
        for row in mulligan["Mulligan"]["values"]
    )
```

If the actual deck slug differs, use `operator["deck_slug"]` or the existing helper pattern in the file.

- [ ] **Step 2: Add universal no-block regression for unknown mechanic qualifier**

Append to `tests/test_universal_wild_no_block_matrix.py`:

```python
def test_unknown_semantic_qualifier_stays_warning_not_apply_block(tmp_path):
    # Use the existing fixture helper in this file. The assertion contract is:
    # - package prepare exits 0
    # - operator_summary technical_status is VALID_PACKAGE
    # - unknown qualifier/mechanic appears in diagnostics, not apply blockers
    result = prepare_fixture_deck_with_source_claim(
        tmp_path,
        deck_name="QualifierUnknown",
        claim={
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_001"],
            "evidence_text_short": "Use the new future mechanic when possible.",
            "source_confidence": "high",
            "semantic_qualifiers": {"state_requirements": ["future_mechanic"]},
        },
    )

    assert result["operator_summary"]["technical_status"] == "VALID_PACKAGE"
    assert result["operator_summary"]["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
```

If no helper exists, create a local helper in the test file using the existing CLI `prepare` pattern from other no-block tests.

- [ ] **Step 3: Run E2E tests**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_universal_wild_no_block_matrix.py
git commit -m "test: prove semantic qualifier e2e boundaries"
```

---

### Task 9: Full Verification And Research Artifact Handling

**Files:**
- Existing uncommitted research: `docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v5/`
- Plan: `docs/superpowers/plans/2026-07-13-contract-spine-slimness-semantic-qualifiers.md`

**Interfaces:**
- Produces a clean branch with plan, research, implementation commits, and passing tests.

- [ ] **Step 1: Validate research package**

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py --fields docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v5\fields.yaml --dir docs\research\2026-07-13-hsconfig-source-contract-logic-brainstorm-v5\results
```

Expected:

```text
Validation passed: 6/6
Average coverage: 100.0%
```

- [ ] **Step 2: Run focused test groups**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_preconfig_context_parity.py tests/test_guide_claim_bundle_parity.py tests/test_semantic_qualifiers.py tests/test_source_claim_conflicts.py -q
```

Expected: PASS.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_surface_authority_split.py tests/test_source_contract_conformance.py tests/test_source_claim_quality_autonomy.py tests/test_apply_authority_boundary.py -q
```

Expected: PASS.

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_universal_wild_no_block_matrix.py -q
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
```

Expected: PASS.

- [ ] **Step 4: Run policy scans**

```powershell
rg -n "Presume.json|Concede.json" src docs .agents -g "!docs/research/**" -g "!docs/superpowers/archive/**"
```

Expected: Any hits must describe legacy/diagnostic/non-normal surfaces, not normal output.

```powershell
rg -n "operator_summary.json" src docs .agents -g "!docs/research/**" -g "!docs/superpowers/archive/**"
```

Expected: Active docs keep `operator_summary.json` as single normal apply authority.

- [ ] **Step 5: Commit plan and research if not already committed**

```powershell
git add docs/research/2026-07-13-hsconfig-source-contract-logic-brainstorm-v5 docs/superpowers/plans/2026-07-13-contract-spine-slimness-semantic-qualifiers.md
git commit -m "docs: plan contract spine semantic qualifier wave"
```

If these files were committed earlier, skip this commit.

- [ ] **Step 6: Final status**

```powershell
git status --short --branch
```

Expected: clean working tree on the implementation branch.

---

## Self-Review

- Spec coverage: The plan covers shared context authority, guide-claim bundle parity, semantic qualifiers, stronger effect-vs-mulligan suppression, broader non-blocking conflict reports, surface intent wording, docs/skill alignment, no-block E2E proof, and research artifact handling.
- Placeholder scan: No placeholder markers or future-fill sections are required for task execution. Where local helper names may vary, the plan gives the fallback implementation boundary and exact assertion contract.
- Type consistency: The main new interfaces are `build_preconfig_context(args)`, `normalize_semantic_qualifiers(claim, card_roles=None)`, `has_qualifier(claim, key, value)`, and `build_claim_conflict_report(claims)`. Later tasks use those same names.
- Scope check: This is one cohesive implementation wave. It intentionally avoids new runtime surfaces, new dependencies, and broad repo cleanup outside the source-contract spine.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-13-contract-spine-slimness-semantic-qualifiers.md`.

Recommended execution: **Subagent-Driven**.

Suggested worker split:

1. Worker A: Task 1 shared preconfig context.
2. Worker B: Task 2 bundle parity sentinel.
3. Worker C: Tasks 3-4 semantic qualifiers and mulligan suppression.
4. Worker D: Task 5 conflict reports.
5. Worker E: Tasks 6-7 surface/docs alignment.
6. Final reviewer: Tasks 8-9 E2E verification, full tests, git status.

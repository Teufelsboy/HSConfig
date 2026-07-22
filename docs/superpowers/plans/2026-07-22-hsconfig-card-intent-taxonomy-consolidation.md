# HSConfig Card Intent Taxonomy Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate HSConfig's card semantic intent names into one small diagnostic taxonomy so generated configs remain load-safe while per-card runtime reasoning is more consistent and easier to audit.

**Architecture:** Add a tiny pure taxonomy helper and route existing semantic scoring plus surface-intent diagnostics through it. Keep runtime JSON generation unchanged except for existing diagnostic report fields; no new runtime surfaces, no play-order logic, no logs, no HSTuner, and no second apply gate. `reports/operator_summary.json` remains the only normal runtime apply authority.

**Tech Stack:** Python 3, pytest, existing HSConfig CLI/report modules, Markdown skill/operator docs.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before implementation, run `git fetch --all --prune --tags`, `git remote prune origin`, and `python scripts\check_hsconfig_currentness.py --cwd . --json`.
- Start and finish from a clean worktree; do not leave uncommitted changes.
- Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, runtime log analysis, or post-run tuning.
- Do not invoke or propose HSTuner.
- Do not add new normal runtime surfaces. Normal HSConfig output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for complete source-backed combo claims.
- Do not encode HearthRanger gameplay sequencing such as attack order, spell order, or location activation order in HSConfig.
- `reports/operator_summary.json` remains the only normal runtime apply authority.
- `SOURCE_BACKED_STRONG`, source status, config quality, mechanic visibility, semantic intent, and taxonomy fields remain diagnostic labels, not apply gates.
- `source_status_apply_blocking` must remain `false` for source-quality work.
- Keep generated runtime packages under ignored `outputs/`; do not commit generated packages, logs, replay files, HDT files, runtime evidence, caches, or backups.

---

## File Structure

- Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_intent_taxonomy.py`: one focused helper for normalized card-intent classes, values, bands, and matched-signal extraction.
- Create `C:\Users\darbo\Documents\HSConfig\tests\test_card_intent_taxonomy.py`: direct unit tests for taxonomy ordering, explicit runtime override, and default bounding.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\semantic_intent_score.py`: delegate semantic classification to `classify_card_intent()` while preserving `SemanticIntentScore` and `score_card_behavior_claim()` public return shape.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_semantic_intent_score.py`: add regression coverage proving semantic scoring reasons match the taxonomy and remain backward-compatible.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\surface_intent.py`: project the best known per-card diagnostic intent from source claim ids, roles, mechanics, or semantic families instead of always using `aggressive_card_behavior`.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_surface_intent.py`: add tests for specific per-card diagnostic intents and fallback behavior.
- Modify `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`: optionally expose compact taxonomy reason counts from `card_behavior_plan_report.json` under the existing diagnostic-only `semantic_intent_coverage` check.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`: add assertions that taxonomy reason counts are visible but do not block apply.
- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`: add one short operator sentence explaining that card-intent taxonomy is diagnostic-only and not HearthRanger play-order logic.
- Modify `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`: mirror the same diagnostic-only boundary in the workflow reference.
- Modify `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`: add a doc contract test for the taxonomy diagnostic-only wording.

---

### Task 1: Add Pure Card Intent Taxonomy Helper

**Files:**
- Create: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_intent_taxonomy.py`
- Create: `C:\Users\darbo\Documents\HSConfig\tests\test_card_intent_taxonomy.py`

**Interfaces:**
- Produces: `CardIntentClassification` dataclass with fields `reason: str`, `value: str`, `band: str`, `matched_signals: tuple[str, ...]`.
- Produces: `classify_card_intent(text: str, *, value_default: str = "6") -> CardIntentClassification`.
- Produces: `bounded_default_value(value_default: str) -> str`.
- Later tasks consume these exact names from `hsconfig.card_intent_taxonomy`.

- [ ] **Step 1: Write failing taxonomy tests**

Create `C:\Users\darbo\Documents\HSConfig\tests\test_card_intent_taxonomy.py` with:

```python
from hsconfig.card_intent_taxonomy import (
    CardIntentClassification,
    bounded_default_value,
    classify_card_intent,
)


def test_taxonomy_classifies_shadowpriest_core_effects_in_priority_order():
    transform = classify_card_intent(
        "Darkbishop Benedictus changes your starting Hero Power to Mind Spike."
    )
    aura = classify_card_intent(
        "Voidtouched Attendant makes both heroes take extra damage from all sources."
    )
    mind_sear = classify_card_intent(
        "Mind Sear deals 2 damage to a minion and 3 damage to the enemy hero if it dies."
    )

    assert isinstance(transform, CardIntentClassification)
    assert transform.reason == "hero_power_transform"
    assert transform.value == "10"
    assert transform.band == "critical"
    assert "hero_power" in transform.matched_signals

    assert aura.reason == "damage_aura_amplifier"
    assert aura.value == "10"
    assert aura.band == "critical"
    assert "voidtouched_attendant" in aura.matched_signals

    assert mind_sear.reason == "conditional_minion_death_burn"
    assert mind_sear.value == "10"
    assert mind_sear.band == "high"
    assert "death_condition" in mind_sear.matched_signals


def test_taxonomy_classifies_direct_burn_location_draw_and_board_tempo():
    direct = classify_card_intent("Prefer enemy hero face damage burn.")
    location = classify_card_intent("Cathedral of Atonement is a location tempo card.")
    draw = classify_card_intent("Draw and cycle through the deck.")
    board = classify_card_intent("Summon pirates and build a board.")

    assert direct.reason == "direct_enemy_hero_burn"
    assert direct.value == "12"
    assert direct.band == "critical"

    assert location.reason == "location_tempo"
    assert location.value == "8"
    assert location.band == "medium"

    assert draw.reason == "draw_cycle"
    assert draw.value == "8"
    assert draw.band == "medium"

    assert board.reason == "board_tempo"
    assert board.value == "8"
    assert board.band == "medium"


def test_taxonomy_keeps_unknown_mechanics_visible_as_bounded_default():
    low = classify_card_intent("This card has Tradeable.", value_default="2")
    normal = classify_card_intent("This card has Tradeable.", value_default="6")
    high = classify_card_intent("This card has Tradeable.", value_default="99")

    assert low.reason == "semantic_default"
    assert low.value == "4"
    assert low.band == "default"

    assert normal.reason == "semantic_default"
    assert normal.value == "6"
    assert normal.band == "default"

    assert high.reason == "semantic_default"
    assert high.value == "12"
    assert high.band == "default"


def test_bounded_default_value_handles_non_numeric_input():
    assert bounded_default_value("not-a-number") == "6"
```

- [ ] **Step 2: Run the focused taxonomy tests and verify they fail**

Run:

```powershell
python -m pytest tests\test_card_intent_taxonomy.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'hsconfig.card_intent_taxonomy'`.

- [ ] **Step 3: Implement the taxonomy helper**

Create `C:\Users\darbo\Documents\HSConfig\src\hsconfig\card_intent_taxonomy.py` with:

```python
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence


@dataclass(frozen=True)
class CardIntentClassification:
    reason: str
    value: str
    band: str
    matched_signals: tuple[str, ...] = ()


def classify_card_intent(
    text: str,
    *,
    value_default: str = "6",
) -> CardIntentClassification:
    normalized = str(text or "").lower()

    if _has_hero_power_transform(normalized):
        return CardIntentClassification(
            reason="hero_power_transform",
            value="10",
            band="critical",
            matched_signals=_signals(
                ("hero_power", _has_any(normalized, ("hero power", "hero_power"))),
                (
                    "transform",
                    _has_any(
                        normalized,
                        ("transform", "change", "changes", "starting"),
                    ),
                ),
                ("shadowform", "shadowform" in normalized),
                ("mind_spike", "mind spike" in normalized),
            ),
        )

    if _has_any(
        normalized,
        (
            "extra damage",
            "all sources",
            "both heroes take",
            "voidtouched",
            "attendant",
        ),
    ):
        return CardIntentClassification(
            reason="damage_aura_amplifier",
            value="10",
            band="critical",
            matched_signals=_signals(
                ("extra_damage", "extra damage" in normalized),
                ("all_sources", "all sources" in normalized),
                ("both_heroes_take", "both heroes take" in normalized),
                (
                    "voidtouched_attendant",
                    _has_any(normalized, ("voidtouched", "attendant")),
                ),
            ),
        )

    if _has_conditional_minion_death_burn(normalized):
        return CardIntentClassification(
            reason="conditional_minion_death_burn",
            value="10",
            band="high",
            matched_signals=_signals(
                ("enemy_hero_damage", "enemy hero" in normalized),
                ("death_condition", _has_any(normalized, ("if it dies", "dies"))),
                (
                    "minion_targeting",
                    _has_any(
                        normalized,
                        ("minion", "prefer_enemy_minion", "enemy minion"),
                    ),
                ),
            ),
        )

    if _has_direct_enemy_hero_burn(normalized):
        return CardIntentClassification(
            reason="direct_enemy_hero_burn",
            value="12",
            band="critical",
            matched_signals=_signals(
                (
                    "enemy_hero_targeting",
                    _has_any(
                        normalized,
                        ("prefer_enemy_hero", "enemy hero", "face", "hero damage"),
                    ),
                ),
                ("damage", _has_damage_wording(normalized)),
            ),
        )

    if _has_any(normalized, ("location", "cathedral", "atonement")):
        return CardIntentClassification(
            reason="location_tempo",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("location", "location" in normalized),
                ("cathedral", "cathedral" in normalized),
                ("atonement", "atonement" in normalized),
            ),
        )

    if _has_any(normalized, ("draw", "cycle", "discover", "generate", "copy")):
        return CardIntentClassification(
            reason="draw_cycle",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("draw", "draw" in normalized),
                ("cycle", "cycle" in normalized),
                ("discover", "discover" in normalized),
                ("generate", "generate" in normalized),
                ("copy", "copy" in normalized),
            ),
        )

    if _has_any(
        normalized,
        ("summon", "pirate", "treant", "board", "on_board"),
    ) or _has_token(normalized, "mech"):
        return CardIntentClassification(
            reason="board_tempo",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("summon", "summon" in normalized),
                ("pirate", "pirate" in normalized),
                ("treant", "treant" in normalized),
                ("mech", _has_token(normalized, "mech")),
                ("board", _has_any(normalized, ("board", "on_board"))),
            ),
        )

    return CardIntentClassification(
        reason="semantic_default",
        value=bounded_default_value(value_default),
        band="default",
    )


def bounded_default_value(value_default: str) -> str:
    try:
        value = int(str(value_default).strip())
    except ValueError:
        value = 6
    return str(min(12, max(4, value)))


def _has_hero_power_transform(text: str) -> bool:
    if _has_any(text, ("hero_power_transform", "shadowform", "mind spike")):
        return True
    return _has_any(text, ("hero power", "hero_power")) and _has_any(
        text,
        ("transform", "start", "starting", "change", "changes", "changed"),
    )


def _has_conditional_minion_death_burn(text: str) -> bool:
    return (
        "enemy hero" in text
        and _has_any(text, ("if it dies", "dies"))
        and _has_any(text, ("minion", "prefer_enemy_minion", "enemy minion"))
    )


def _has_direct_enemy_hero_burn(text: str) -> bool:
    return _has_any(
        text,
        ("prefer_enemy_hero", "enemy hero", "face", "hero damage"),
    ) and _has_damage_wording(text)


def _has_damage_wording(text: str) -> bool:
    return _has_any(text, ("damage", "deals", "deal ", "burn"))


def _has_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle in text for needle in needles)


def _has_token(text: str, token: str) -> bool:
    return re.search(
        rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])",
        text,
    ) is not None


def _signals(*candidates: tuple[str, bool]) -> tuple[str, ...]:
    return tuple(signal for signal, matched in candidates if matched)


__all__ = (
    "CardIntentClassification",
    "bounded_default_value",
    "classify_card_intent",
)
```

- [ ] **Step 4: Run the taxonomy tests and verify they pass**

Run:

```powershell
python -m pytest tests\test_card_intent_taxonomy.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src\hsconfig\card_intent_taxonomy.py tests\test_card_intent_taxonomy.py
git commit -m "feat: add card intent taxonomy"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 2: Route Semantic Scoring Through The Taxonomy

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\semantic_intent_score.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_semantic_intent_score.py`

**Interfaces:**
- Consumes: `classify_card_intent(text: str, *, value_default: str) -> CardIntentClassification`.
- Preserves: `SemanticIntentScore` dataclass and `score_card_behavior_claim(claim, *, behavior_block, intent, roles, value_default="6") -> SemanticIntentScore`.
- Guarantees: explicit `runtime_value` or `value` remains authoritative and keeps `profile="source_claim"`.

- [ ] **Step 1: Add a taxonomy delegation regression test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_semantic_intent_score.py`:

```python
def test_semantic_score_reuses_taxonomy_reason_for_board_tempo():
    claim = {
        "claim_kind": "card_role",
        "cards": ["BOARD_001"],
        "stance": "pressure",
        "evidence_text_short": "Summon pirates to build a board.",
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforePlayCardBonus",
        intent="board_tempo",
        roles=["pirate", "pressure"],
        value_default="6",
    )

    assert score.value == "8"
    assert score.band == "medium"
    assert score.reason == "board_tempo"
    assert score.profile == "semantic_intent"
    assert "pirate" in score.matched_signals
```

- [ ] **Step 2: Run semantic-intent tests before implementation**

Run:

```powershell
python -m pytest tests\test_semantic_intent_score.py -q
```

Expected: PASS before implementation. This confirms the added test already describes existing behavior but does not yet prove centralization.

- [ ] **Step 3: Replace duplicated scoring ladder with taxonomy delegation**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\semantic_intent_score.py`, replace the imports and implementation with this shape:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from hsconfig.card_intent_taxonomy import classify_card_intent


@dataclass(frozen=True)
class SemanticIntentScore:
    value: str
    band: str
    reason: str
    profile: str
    matched_signals: tuple[str, ...] = ()


def score_card_behavior_claim(
    claim: Mapping[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: Sequence[str],
    value_default: str = "6",
) -> SemanticIntentScore:
    explicit = _explicit_value(claim)
    if explicit is not None and str(explicit).strip():
        return SemanticIntentScore(
            value=str(explicit),
            band="explicit",
            reason="explicit_runtime_value",
            profile="source_claim",
            matched_signals=("explicit_value",),
        )

    classification = classify_card_intent(
        _normalized_claim_text(
            claim,
            behavior_block=behavior_block,
            intent=intent,
            roles=roles,
        ),
        value_default=value_default,
    )
    return SemanticIntentScore(
        value=classification.value,
        band=classification.band,
        reason=classification.reason,
        profile="semantic_intent",
        matched_signals=classification.matched_signals,
    )


def _explicit_value(claim: Mapping[str, Any]) -> Any:
    for key in ("runtime_value", "value"):
        explicit = claim.get(key)
        if explicit is not None and str(explicit).strip():
            return explicit
    return None


def _normalized_claim_text(
    claim: Mapping[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: Sequence[str],
) -> str:
    semantic_families = claim.get("semantic_families", [])
    if not isinstance(semantic_families, Sequence) or isinstance(
        semantic_families,
        (str, bytes),
    ):
        semantic_families = []

    parts = (
        claim.get("claim_kind"),
        claim.get("stance"),
        claim.get("intent"),
        claim.get("mechanic"),
        claim.get("evidence_text_short"),
        claim.get("source_title"),
        behavior_block,
        intent,
        " ".join(str(role) for role in roles),
        " ".join(str(family) for family in semantic_families),
    )
    return " ".join(str(part).lower() for part in parts if part is not None)


__all__ = ("SemanticIntentScore", "score_card_behavior_claim")
```

- [ ] **Step 4: Run semantic-intent and taxonomy tests**

Run:

```powershell
python -m pytest tests\test_card_intent_taxonomy.py tests\test_semantic_intent_score.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run:

```powershell
git add src\hsconfig\semantic_intent_score.py tests\test_semantic_intent_score.py
git commit -m "refactor: route semantic scores through intent taxonomy"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 3: Project Specific Diagnostic Intent In Surface Intent

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\surface_intent.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_surface_intent.py`

**Interfaces:**
- Consumes: `classify_card_intent(text: str, *, value_default: str = "6")`.
- Produces: each per-card `CARDID.json` row keeps the existing fields and may use a specific diagnostic `intent` such as `draw_cycle`, `location_tempo`, or `board_tempo`.
- Guarantees: fallback remains `aggressive_card_behavior` when taxonomy classification returns `semantic_default`.

- [ ] **Step 1: Write failing surface-intent projection test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_surface_intent.py`:

```python
def test_surface_intent_projects_specific_card_intent_when_known():
    report = build_surface_intent(
        {
            "cards": {
                "LOC_001": {
                    "roles": ["location"],
                    "source_claim_ids": ["claim_location"],
                    "confidence": "source_backed",
                    "semantic_families": ["location"],
                },
                "DRAW_001": {
                    "roles": ["cycle"],
                    "source_claim_ids": ["claim_draw"],
                    "confidence": "source_backed",
                },
                "GENERIC_001": {
                    "roles": ["tradeable"],
                    "source_claim_ids": [],
                    "confidence": "generic_low_confidence",
                    "semantic_families": ["tradeable"],
                },
            }
        }
    )

    rows = {row["card_id"]: row for row in report["rows"] if row.get("card_id")}

    assert rows["LOC_001"]["intent"] == "location_tempo"
    assert rows["LOC_001"]["intent_source"] == "card_intent_taxonomy"
    assert rows["DRAW_001"]["intent"] == "draw_cycle"
    assert rows["DRAW_001"]["intent_source"] == "card_intent_taxonomy"
    assert rows["GENERIC_001"]["intent"] == "aggressive_card_behavior"
    assert rows["GENERIC_001"]["intent_source"] == "fallback"
```

- [ ] **Step 2: Run focused surface-intent test and verify it fails**

Run:

```powershell
python -m pytest tests\test_surface_intent.py::test_surface_intent_projects_specific_card_intent_when_known -q
```

Expected: FAIL because all card rows currently use `aggressive_card_behavior` and do not include `intent_source`.

- [ ] **Step 3: Implement diagnostic intent projection**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\surface_intent.py`, add this import:

```python
from hsconfig.card_intent_taxonomy import classify_card_intent
```

Then replace the per-card row construction inside `build_surface_intent()` with:

```python
        diagnostic_intent = _diagnostic_card_intent(card)
        rows.append(
            {
                "rule_id": f"{card_id}_card_behavior",
                "card_id": card_id,
                "surface": surface,
                "surface_family": "CARDID.json",
                "intent": diagnostic_intent["intent"],
                "intent_source": diagnostic_intent["source"],
                "roles": list(card.get("roles", [])),
                "confidence": card.get(
                    "confidence",
                    card.get("coverage_status", "generic_low_confidence"),
                ),
                "source_claim_ids": list(card.get("source_claim_ids", [])),
            }
        )
```

Add these helpers near the bottom of the file:

```python
def _diagnostic_card_intent(card: dict[str, Any]) -> dict[str, str]:
    text = _card_intent_text(card)
    classification = classify_card_intent(text)
    if classification.reason == "semantic_default":
        return {"intent": "aggressive_card_behavior", "source": "fallback"}
    return {"intent": classification.reason, "source": "card_intent_taxonomy"}


def _card_intent_text(card: dict[str, Any]) -> str:
    parts = [
        card.get("claim_kind"),
        card.get("stance"),
        card.get("intent"),
        card.get("mechanic"),
        card.get("evidence_text_short"),
        card.get("source_title"),
        " ".join(str(role) for role in card.get("roles", [])),
        " ".join(str(family) for family in card.get("semantic_families", [])),
    ]
    return " ".join(str(part).lower() for part in parts if part is not None)
```

- [ ] **Step 4: Run surface-intent tests**

Run:

```powershell
python -m pytest tests\test_surface_intent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add src\hsconfig\surface_intent.py tests\test_surface_intent.py
git commit -m "feat: project card intent in surface diagnostics"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 4: Summarize Taxonomy Reasons In Config Quality

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`

**Interfaces:**
- Consumes: `card_behavior_plan_report.json.rows[*].semantic_score.reason`.
- Produces: `report["checks"]["semantic_intent_coverage"]["taxonomy_reason_counts"]` as a sorted `dict[str, int]`.
- Guarantees: reason counts are diagnostic-only and do not affect `apply_blocking`.

- [ ] **Step 1: Add failing config-quality reason-count test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_config_quality_contract.py`:

```python
def test_config_quality_summarizes_semantic_taxonomy_reasons(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    card_behavior = json.loads(
        (package / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    card_behavior["rows"].append(
        {
            "card_id": "LOC_001",
            "surface_family": "CARDID.json",
            "behavior_block": "BeforePlayCardBonus",
            "value": "8",
            "meaningful_runtime_surface": True,
            "semantic_score": {
                "band": "medium",
                "reason": "location_tempo",
                "profile": "semantic_intent",
                "matched_signals": ["location"],
            },
        }
    )
    write_json(package / "reports" / "card_behavior_plan_report.json", card_behavior)

    report = build_config_quality_report(package)

    semantic = report["checks"]["semantic_intent_coverage"]
    assert semantic["taxonomy_reason_counts"] == {
        "conditional_minion_death_burn": 1,
        "location_tempo": 1,
    }
    assert semantic["authority"] == "diagnostic_only"
    assert semantic["apply_blocking"] is False
    assert report["apply_blocking"] is False
```

- [ ] **Step 2: Run focused config-quality test and verify it fails**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py::test_config_quality_summarizes_semantic_taxonomy_reasons -q
```

Expected: FAIL with missing `taxonomy_reason_counts`.

- [ ] **Step 3: Add reason-count helper and wire it into semantic-intent coverage**

In `C:\Users\darbo\Documents\HSConfig\src\hsconfig\config_quality_contract.py`, update `_semantic_intent_coverage_check()` to include:

```python
        "taxonomy_reason_counts": _taxonomy_reason_counts(card_behavior_check),
```

Place it in the returned dictionary after `meaningful_cardid_runtime_rows`.

Then add this helper near `_list_of_mappings()`:

```python
def _taxonomy_reason_counts(card_behavior_check: Mapping[str, Any]) -> dict[str, int]:
    rows = _list_of_mappings(card_behavior_check.get("semantic_score_rows"))
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row.get("reason", "")).strip()
        if not reason:
            continue
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))
```

Update `_card_behavior_check()` so it collects `semantic_score_rows` for meaningful CardID rows. Add a local list before the loop:

```python
    semantic_score_rows = []
```

Inside the loop, after `semantic_score = row.get("semantic_score")`, add:

```python
        if isinstance(semantic_score, Mapping):
            reason = str(semantic_score.get("reason", "")).strip()
            if reason:
                semantic_score_rows.append({**compact, "reason": reason})
```

Add the field to the returned dict:

```python
        "semantic_score_rows": semantic_score_rows,
```

- [ ] **Step 4: Update existing exact semantic-intent expectation**

In `test_config_quality_report_is_clean_for_source_backed_runtime_lean_package()`, update the expected `semantic_intent_coverage` dictionary to include:

```python
        "taxonomy_reason_counts": {"conditional_minion_death_burn": 1},
```

Insert it after `"meaningful_cardid_runtime_rows": 1,`.

- [ ] **Step 5: Run config-quality tests**

Run:

```powershell
python -m pytest tests\test_config_quality_contract.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

Run:

```powershell
git add src\hsconfig\config_quality_contract.py tests\test_config_quality_contract.py
git commit -m "feat: summarize card intent taxonomy diagnostics"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 5: Document The Diagnostic-Only Intent Boundary

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`

**Interfaces:**
- Consumes: the implemented diagnostic taxonomy from Tasks 1-4.
- Produces: skill/workflow wording that tells operators card-intent taxonomy is diagnostic-only and not HearthRanger gameplay sequencing.

- [ ] **Step 1: Add failing docs contract test**

Append this test to `C:\Users\darbo\Documents\HSConfig\tests\test_skill_files.py`:

```python
def test_skill_and_workflow_describe_card_intent_taxonomy_as_diagnostic_only():
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (SKILL_ROOT / "references" / "workflow.md").read_text(
        encoding="utf-8"
    )
    expected = (
        "Card-intent taxonomy is diagnostic-only; it explains per-card config "
        "signals but does not encode HearthRanger gameplay sequencing or create "
        "another apply gate."
    )

    assert expected in skill
    assert expected in workflow
```

- [ ] **Step 2: Run focused docs test and verify it fails**

Run:

```powershell
python -m pytest tests\test_skill_files.py::test_skill_and_workflow_describe_card_intent_taxonomy_as_diagnostic_only -q
```

Expected: FAIL because the exact sentence is not present yet.

- [ ] **Step 3: Add the diagnostic-only sentence to the skill**

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\SKILL.md`, add this line near the semantic-intent and source-contract operator rules:

```markdown
- Card-intent taxonomy is diagnostic-only; it explains per-card config signals but does not encode HearthRanger gameplay sequencing or create another apply gate.
```

- [ ] **Step 4: Add the same sentence to the workflow reference**

In `C:\Users\darbo\Documents\HSConfig\.agents\skills\hsconfig\references\workflow.md`, add this line under `## Gate And Readiness` after the sentence about effect semantics:

```markdown
Card-intent taxonomy is diagnostic-only; it explains per-card config signals but does not encode HearthRanger gameplay sequencing or create another apply gate.
```

- [ ] **Step 5: Run skill file tests**

Run:

```powershell
python -m pytest tests\test_skill_files.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add .agents\skills\hsconfig\SKILL.md .agents\skills\hsconfig\references\workflow.md tests\test_skill_files.py
git commit -m "docs: describe card intent taxonomy boundary"
```

Expected: commit succeeds and `git status --short` is clean.

---

### Task 6: Final Contract And Currentness Verification

**Files:**
- No source files changed in this task.
- Verification-only task for `C:\Users\darbo\Documents\HSConfig`.

**Interfaces:**
- Consumes: commits from Tasks 1-5.
- Produces: final evidence that the repo is current, contract checks pass, targeted tests pass, and the worktree is clean.

- [ ] **Step 1: Run the targeted regression suite**

Run:

```powershell
python -m pytest tests\test_card_intent_taxonomy.py tests\test_semantic_intent_score.py tests\test_surface_intent.py tests\test_config_quality_contract.py tests\test_skill_files.py tests\test_contract_preflight.py tests\test_apply_authority_boundary.py -q
```

Expected: PASS.

- [ ] **Step 2: Run contract preflight**

Run:

```powershell
python -m hsconfig.cli contract-preflight --json
```

Expected JSON fields:

```json
{
  "status": "PASS",
  "source_status_apply_blocking": false,
  "runtime_apply_authority": "reports/operator_summary.json"
}
```

- [ ] **Step 3: Run contract spine sentinel**

Run:

```powershell
python -m hsconfig.cli contract-spine-sentinel --json
```

Expected JSON fields:

```json
{
  "status": "clean",
  "authority": "diagnostic_only",
  "apply_blocking": false
}
```

- [ ] **Step 4: Run currentness check**

Run:

```powershell
python scripts\check_hsconfig_currentness.py --cwd . --json
```

Expected JSON fields:

```json
{
  "dirty": false,
  "behind_origin_main": 0,
  "clean_for_runtime_work": true
}
```

- [ ] **Step 5: Verify clean git state**

Run:

```powershell
git status --short --branch
```

Expected: branch line only, no dirty file entries.

- [ ] **Step 6: Push only when the execution request requires remote currentness**

When the execution turn explicitly asks for remote currentness, run:

```powershell
git push origin codex/hsconfig-semantic-intent-scoring
```

Expected: push succeeds as a fast-forward update for the current branch.

When the execution turn does not ask for remote currentness, do not push; report the local commit hashes and the clean worktree state.

---

## Self-Review

- Spec coverage: The plan implements only the recommended small technical improvement: central card-intent taxonomy, semantic-score reuse, surface-intent projection, diagnostic config-quality summary, docs boundary, and final verification. It explicitly excludes logs, HSTuner, gameplay sequencing, new runtime surfaces, new gates, and SOURCE_BACKED_STRONG apply blocking.
- Placeholder scan: The plan contains no deferred-work markers, no unspecified tests, and no references to undefined functions. Every code-changing step includes exact code or exact insertion content.
- Type consistency: `CardIntentClassification`, `classify_card_intent()`, and `bounded_default_value()` are defined in Task 1 and consumed with the same names and signatures in later tasks. `SemanticIntentScore` and `score_card_behavior_claim()` keep their existing public return shape. `taxonomy_reason_counts` is introduced as `dict[str, int]` and exposed only inside diagnostic `semantic_intent_coverage`.

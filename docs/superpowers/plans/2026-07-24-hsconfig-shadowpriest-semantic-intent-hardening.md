# HSConfig ShadowPriest Semantic Intent Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining generic ShadowPriest card-intent fallbacks while preserving the current load-safe HSConfig runtime contract.

**Architecture:** Keep the implementation narrow: extend the existing diagnostic card-intent taxonomy and reuse it from both card-behavior scoring and `surface_intent.json`. Do not add new VisionAI runtime surfaces, do not create another apply gate, and do not add post-game or HSTuner logic.

**Tech Stack:** Python, pytest, existing `hsconfig` CLI/package-builder modules, existing JSON reports under `outputs/<DeckName>/04_package/reports`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Before runtime-facing verification, run `git fetch --all --prune --tags`, `python scripts/check_hsconfig_currentness.py --cwd . --json`, and `git status --short --branch`.
- Keep the worktree clean at handoff.
- Runtime writes remain allowed only through `hsconfig apply` or `hsconfig configure --apply`.
- `reports/operator_summary.json` remains the only normal apply authority.
- `SOURCE_BACKED_STRONG` stays an evidence-quality label, not a generation or apply gate.
- `source_status_apply_blocking` must remain `false` for source-quality work.
- Normal runtime output remains `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only when exact ordered combo evidence exists.
- Do not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`.
- Do not add HSTuner, replay parsing, winrate parsing, log tuning, or post-game tuning.
- Do not turn diagnostic warnings into hard blockers.
- Do not keep `SW_448` Darkbishop Benedictus in Mulligan without explicit opening-hand source text.
- No new third-party dependencies.

---

## File Structure

- Modify `src/hsconfig/card_intent_taxonomy.py`: add compact recognizers for ShadowPriest card mechanics that are already present in static card text or exact card identity.
- Modify `src/hsconfig/surface_intent.py`: include card name and mechanic families in diagnostic intent text so surface projection can use the same taxonomy without guessing.
- Modify `tests/test_card_intent_taxonomy.py`: lock the new taxonomy reasons and priority order.
- Modify `tests/test_semantic_intent_score.py`: prove behavior scoring no longer falls back to `semantic_default` for the affected ShadowPriest claims.
- Modify `tests/test_surface_intent.py`: prove `surface_intent.json` projects specific taxonomy reasons for the current ShadowPriest fallback cards.
- Modify `tests/test_shadowpriest_e2e.py`: add package-level regression coverage that the real ShadowPriest strong fixture has no semantic-default CardID runtime rows for the known cards and no fallback surface-intent rows for known mechanics.
- Modify `.agents/skills/hsconfig/references/card-behavior-policy.md`: document that the taxonomy is diagnostic/scoring only and must not introduce unsupported runtime surfaces.

---

### Task 1: Lock ShadowPriest Taxonomy Expectations

**Files:**
- Modify: `tests/test_card_intent_taxonomy.py`
- Modify: `tests/test_semantic_intent_score.py`

**Interfaces:**
- Consumes: `classify_card_intent(text: str, *, value_default: str = "6") -> CardIntentClassification`.
- Consumes: `score_card_behavior_claim(claim, *, behavior_block, intent, roles, value_default="6") -> SemanticIntentScore`.
- Produces: expected taxonomy reason strings used by later tasks:
  - `reciprocal_hero_burn`
  - `self_damage_resource`
  - `self_damage_liability_body`
  - `opponent_damage_discount_tempo`
  - `hero_power_cost_aura`

- [ ] **Step 1: Add failing taxonomy tests**

Append this code to `tests/test_card_intent_taxonomy.py`:

```python

def test_taxonomy_classifies_shadowpriest_reciprocal_and_self_damage_semantics():
    shadowbomber = classify_card_intent(
        "<b>Battlecry:</b> Deal 3 damage to each hero. battlecry BATTLECRY"
    )
    acupuncture = classify_card_intent("[x]Deal $4 damage to both heroes.")
    raise_dead = classify_card_intent(
        "Deal $3 damage to your hero. Return two friendly minions that died this game to your hand."
    )
    brain_masseuse = classify_card_intent(
        "[x]Whenever this minion takes damage, also deal that amount to your hero. TRIGGER_VISUAL"
    )
    felwing = classify_card_intent(
        "Costs (1) less for each damage dealt to your opponent this turn."
    )

    assert shadowbomber.reason == "reciprocal_hero_burn"
    assert shadowbomber.value == "10"
    assert shadowbomber.band == "high"
    assert "each_hero" in shadowbomber.matched_signals

    assert acupuncture.reason == "reciprocal_hero_burn"
    assert acupuncture.value == "10"
    assert acupuncture.band == "high"
    assert "both_heroes" in acupuncture.matched_signals

    assert raise_dead.reason == "self_damage_resource"
    assert raise_dead.value == "8"
    assert raise_dead.band == "medium"
    assert "return_dead_friendly_minions" in raise_dead.matched_signals

    assert brain_masseuse.reason == "self_damage_liability_body"
    assert brain_masseuse.value == "6"
    assert brain_masseuse.band == "medium"
    assert "takes_damage_reflects_to_own_hero" in brain_masseuse.matched_signals

    assert felwing.reason == "opponent_damage_discount_tempo"
    assert felwing.value == "8"
    assert felwing.band == "medium"
    assert "opponent_damage_this_turn" in felwing.matched_signals


def test_taxonomy_classifies_shadowpriest_card_identity_when_surface_has_no_card_text():
    assert classify_card_intent("Shadowbomber battlecry damage minion pressure").reason == (
        "reciprocal_hero_burn"
    )
    assert classify_card_intent("Acupuncture combo_piece damage pressure spell").reason == (
        "reciprocal_hero_burn"
    )
    assert classify_card_intent("Raise Dead damage pressure spell").reason == (
        "self_damage_resource"
    )
    assert classify_card_intent("Brain Masseuse damage minion pressure").reason == (
        "self_damage_liability_body"
    )
    assert classify_card_intent("Frenzied Felwing damage minion pressure").reason == (
        "opponent_damage_discount_tempo"
    )
    assert classify_card_intent("Papercraft Angel aura hero_power minion pressure").reason == (
        "hero_power_cost_aura"
    )
    assert classify_card_intent("Mind Blast combo_piece damage pressure spell").reason == (
        "direct_enemy_hero_burn"
    )
    assert classify_card_intent("Mind Sear damage pressure spell").reason == (
        "conditional_minion_death_burn"
    )


def test_damage_aura_still_wins_before_reciprocal_hero_burn():
    classification = classify_card_intent(
        "Voidtouched Attendant makes both heroes take extra damage from all sources."
    )

    assert classification.reason == "damage_aura_amplifier"
    assert classification.value == "10"
    assert classification.band == "critical"
```

- [ ] **Step 2: Run taxonomy tests and verify they fail**

Run:

```powershell
pytest tests/test_card_intent_taxonomy.py -q
```

Expected: FAIL. The new assertions should currently receive `semantic_default` for at least `Shadowbomber`, `Acupuncture`, `Raise Dead`, `Brain Masseuse`, `Frenzied Felwing`, and `Papercraft Angel` identity-only inputs.

- [ ] **Step 3: Add failing semantic score tests**

Append this code to `tests/test_semantic_intent_score.py`:

```python

def test_shadowpriest_static_damage_claims_receive_specific_semantic_scores():
    cases = [
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["GVG_009"],
                "evidence_text_short": "<b>Battlecry:</b> Deal 3 damage to each hero. battlecry BATTLECRY",
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "reciprocal_hero_burn",
            "10",
            "high",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["SCH_514"],
                "evidence_text_short": (
                    "Deal $3 damage to your hero. Return two friendly minions that died this game to your hand."
                ),
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "self_damage_resource",
            "8",
            "medium",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["VAC_419"],
                "evidence_text_short": "[x]Deal $4 damage to both heroes.",
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "reciprocal_hero_burn",
            "10",
            "high",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["VAC_512"],
                "evidence_text_short": (
                    "[x]Whenever this minion takes damage, also deal that amount to your hero. TRIGGER_VISUAL"
                ),
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "self_damage_liability_body",
            "6",
            "medium",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["YOD_032"],
                "evidence_text_short": (
                    "Costs (1) less for each damage dealt to your opponent this turn."
                ),
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "opponent_damage_discount_tempo",
            "8",
            "medium",
        ),
    ]

    for claim, block, intent, roles, reason, value, band in cases:
        score = score_card_behavior_claim(
            claim,
            behavior_block=block,
            intent=intent,
            roles=roles,
            value_default="6",
        )
        assert score.reason == reason
        assert score.value == value
        assert score.band == band
        assert score.profile == "semantic_intent"
        assert score.matched_signals
```

- [ ] **Step 4: Run semantic score tests and verify they fail**

Run:

```powershell
pytest tests/test_semantic_intent_score.py -q
```

Expected: FAIL. The new cases should currently fall back to `semantic_default`.

- [ ] **Step 5: Commit test-only failing state**

Do not commit failing tests if this task is executed inside the main branch. If executing in an isolated feature worktree, commit only when project practice allows red commits:

```powershell
git add tests/test_card_intent_taxonomy.py tests/test_semantic_intent_score.py
git commit -m "test: lock shadowpriest semantic intent gaps"
```

Expected if committed: one commit containing only tests.

---

### Task 2: Implement Minimal Card Intent Taxonomy Extensions

**Files:**
- Modify: `src/hsconfig/card_intent_taxonomy.py`

**Interfaces:**
- Consumes: test expectations from Task 1.
- Produces: `classify_card_intent()` recognizes ShadowPriest mechanics without returning `semantic_default` for the known cases.

- [ ] **Step 1: Insert taxonomy branches in priority order**

In `src/hsconfig/card_intent_taxonomy.py`, insert the following branches inside `classify_card_intent()` after the existing conditional minion death burn branch and before the existing direct enemy hero burn branch:

```python
    if _has_self_damage_resource(normalized):
        return CardIntentClassification(
            reason="self_damage_resource",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("raise_dead", "raise dead" in normalized),
                ("self_damage", _has_self_damage_to_own_hero(normalized)),
                (
                    "return_dead_friendly_minions",
                    _has_any(
                        normalized,
                        (
                            "return two friendly minions",
                            "friendly minions that died",
                            "died this game to your hand",
                        ),
                    ),
                ),
            ),
        )

    if _has_opponent_damage_discount_tempo(normalized):
        return CardIntentClassification(
            reason="opponent_damage_discount_tempo",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("frenzied_felwing", "frenzied felwing" in normalized),
                ("cost_reduction", _has_any(normalized, ("costs (1) less", "costs less"))),
                (
                    "opponent_damage_this_turn",
                    _has_any(
                        normalized,
                        (
                            "damage dealt to your opponent this turn",
                            "opponent this turn",
                            "opponent_damage",
                        ),
                    ),
                ),
            ),
        )

    if _has_self_damage_liability_body(normalized):
        return CardIntentClassification(
            reason="self_damage_liability_body",
            value="6",
            band="medium",
            matched_signals=_signals(
                ("brain_masseuse", "brain masseuse" in normalized),
                (
                    "takes_damage_reflects_to_own_hero",
                    _has_any(
                        normalized,
                        (
                            "whenever this minion takes damage",
                            "also deal that amount to your hero",
                            "takes damage",
                        ),
                    )
                    and _has_self_damage_to_own_hero(normalized),
                ),
            ),
        )

    if _has_hero_power_cost_aura(normalized):
        return CardIntentClassification(
            reason="hero_power_cost_aura",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("papercraft_angel", "papercraft angel" in normalized),
                ("hero_power", _has_any(normalized, ("hero power", "hero_power"))),
                ("cost_zero", _has_any(normalized, ("costs (0)", "costs 0", "cost 0"))),
            ),
        )
```

Then insert this reciprocal branch after the direct enemy hero burn branch and before the location branch:

```python
    if _has_reciprocal_hero_burn(normalized):
        return CardIntentClassification(
            reason="reciprocal_hero_burn",
            value="10",
            band="high",
            matched_signals=_signals(
                ("shadowbomber", "shadowbomber" in normalized),
                ("acupuncture", "acupuncture" in normalized),
                ("each_hero", "each hero" in normalized),
                ("both_heroes", "both heroes" in normalized),
                ("damage", _has_damage_wording(normalized)),
            ),
        )
```

- [ ] **Step 2: Extend existing helper predicates**

In the same file, replace `_has_conditional_minion_death_burn()` with:

```python
def _has_conditional_minion_death_burn(text: str) -> bool:
    if "mind sear" in text:
        return True
    return (
        "enemy hero" in text
        and _has_any(text, ("if it dies", "dies"))
        and _has_any(text, ("minion", "prefer_enemy_minion", "enemy minion"))
    )
```

Replace `_has_direct_enemy_hero_burn()` with:

```python
def _has_direct_enemy_hero_burn(text: str) -> bool:
    if "mind blast" in text:
        return True
    return any(
        _has_phrase_or_token(text, needle)
        for needle in ("prefer_enemy_hero", "enemy hero", "face", "hero damage")
    ) and _has_damage_wording(text)
```

Add these helpers after `_has_direct_enemy_hero_burn()`:

```python
def _has_reciprocal_hero_burn(text: str) -> bool:
    if _has_any(text, ("shadowbomber", "acupuncture")):
        return True
    return _has_damage_wording(text) and _has_any(
        text,
        ("each hero", "both heroes"),
    )


def _has_self_damage_resource(text: str) -> bool:
    if "raise dead" in text:
        return True
    return _has_self_damage_to_own_hero(text) and _has_any(
        text,
        (
            "return two friendly minions",
            "friendly minions that died",
            "died this game to your hand",
        ),
    )


def _has_opponent_damage_discount_tempo(text: str) -> bool:
    if "frenzied felwing" in text:
        return True
    return _has_any(text, ("costs (1) less", "costs less")) and _has_any(
        text,
        (
            "damage dealt to your opponent this turn",
            "opponent this turn",
            "opponent_damage",
        ),
    )


def _has_self_damage_liability_body(text: str) -> bool:
    if "brain masseuse" in text:
        return True
    return _has_any(
        text,
        ("whenever this minion takes damage", "also deal that amount to your hero"),
    ) and _has_self_damage_to_own_hero(text)


def _has_hero_power_cost_aura(text: str) -> bool:
    if "papercraft angel" in text:
        return True
    return _has_any(text, ("hero power", "hero_power")) and _has_any(
        text,
        ("costs (0)", "costs 0", "cost 0", "free hero power"),
    )


def _has_self_damage_to_own_hero(text: str) -> bool:
    return _has_any(
        text,
        (
            "damage to your hero",
            "deal that amount to your hero",
            "your hero",
        ),
    ) and _has_damage_wording(text)
```

- [ ] **Step 3: Run Task 1 tests**

Run:

```powershell
pytest tests/test_card_intent_taxonomy.py tests/test_semantic_intent_score.py -q
```

Expected: PASS.

- [ ] **Step 4: Run router regression tests**

Run:

```powershell
pytest tests/test_card_behavior_router.py tests/test_config_quality_contract.py -q
```

Expected: PASS. Existing semantics for `Mind Sear`, `Voidtouched Attendant`, `Darkbishop Benedictus`, locations, Discover, Choose One, unsupported blocks, and diagnostic quality reports must remain unchanged except for taxonomy reason counts where new tests explicitly expect the new reasons.

- [ ] **Step 5: Commit taxonomy implementation**

```powershell
git add src/hsconfig/card_intent_taxonomy.py tests/test_card_intent_taxonomy.py tests/test_semantic_intent_score.py
git commit -m "feat: classify shadowpriest semantic intent"
```

Expected: one commit with taxonomy code and tests.

---

### Task 3: Project Specific Intent Into surface_intent.json

**Files:**
- Modify: `src/hsconfig/surface_intent.py`
- Modify: `tests/test_surface_intent.py`

**Interfaces:**
- Consumes: `classify_card_intent()` reasons from Task 2.
- Produces: `_card_intent_text(card: dict[str, Any]) -> str` includes enough existing contract context for taxonomy classification.
- Produces: `build_surface_intent(contract)` returns `intent_source="card_intent_taxonomy"` for known ShadowPriest cards instead of fallback.

- [ ] **Step 1: Add failing surface-intent projection test**

Append this code to `tests/test_surface_intent.py`:

```python

def test_surface_intent_projects_shadowpriest_specific_card_intents_without_fallback():
    report = build_surface_intent(
        {
            "cards": {
                "DS1_233": {
                    "name": "Mind Blast",
                    "roles": ["combo_piece", "damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "GVG_009": {
                    "name": "Shadowbomber",
                    "roles": ["battlecry", "damage", "minion", "pressure"],
                    "semantic_families": ["battlecry", "damage", "minion"],
                    "mechanic_families": ["battlecry", "damage", "minion"],
                },
                "NX2_019": {
                    "name": "Mind Sear",
                    "roles": ["damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "SCH_514": {
                    "name": "Raise Dead",
                    "roles": ["damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "SW_446": {
                    "name": "Voidtouched Attendant",
                    "roles": ["aura", "damage", "minion", "pressure"],
                    "semantic_families": ["aura", "damage", "minion"],
                    "mechanic_families": ["damage", "minion"],
                },
                "TOY_381": {
                    "name": "Papercraft Angel",
                    "roles": ["aura", "combo_piece", "hero_power", "minion", "pressure"],
                    "semantic_families": ["aura", "hero_power", "minion"],
                    "mechanic_families": ["minion"],
                },
                "VAC_419": {
                    "name": "Acupuncture",
                    "roles": ["combo_piece", "damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "VAC_512": {
                    "name": "Brain Masseuse",
                    "roles": ["damage", "minion", "pressure", "trigger_visual"],
                    "semantic_families": ["damage", "minion", "trigger_visual"],
                    "mechanic_families": ["damage", "minion"],
                },
                "YOD_032": {
                    "name": "Frenzied Felwing",
                    "roles": ["damage", "minion", "pressure"],
                    "semantic_families": ["damage", "minion"],
                    "mechanic_families": ["damage", "minion"],
                },
            }
        }
    )

    rows = {row["card_id"]: row for row in report["rows"] if row.get("card_id")}

    assert rows["DS1_233"]["intent"] == "direct_enemy_hero_burn"
    assert rows["GVG_009"]["intent"] == "reciprocal_hero_burn"
    assert rows["NX2_019"]["intent"] == "conditional_minion_death_burn"
    assert rows["SCH_514"]["intent"] == "self_damage_resource"
    assert rows["SW_446"]["intent"] == "damage_aura_amplifier"
    assert rows["TOY_381"]["intent"] == "hero_power_cost_aura"
    assert rows["VAC_419"]["intent"] == "reciprocal_hero_burn"
    assert rows["VAC_512"]["intent"] == "self_damage_liability_body"
    assert rows["YOD_032"]["intent"] == "opponent_damage_discount_tempo"
    assert all(row["intent_source"] == "card_intent_taxonomy" for row in rows.values())
```

- [ ] **Step 2: Run surface-intent tests and verify they fail**

Run:

```powershell
pytest tests/test_surface_intent.py -q
```

Expected: FAIL because `_card_intent_text()` currently omits card `name` and `mechanic_families`, leaving some rows as fallback.

- [ ] **Step 3: Extend surface intent text using existing contract fields**

In `src/hsconfig/surface_intent.py`, replace `_card_intent_text()` with:

```python
def _card_intent_text(card: dict[str, Any]) -> str:
    parts = [
        card.get("name"),
        card.get("claim_kind"),
        card.get("stance"),
        card.get("intent"),
        card.get("mechanic"),
        card.get("evidence_text_short"),
        card.get("source_title"),
        " ".join(str(role) for role in card.get("roles", [])),
        " ".join(str(family) for family in card.get("semantic_families", [])),
        " ".join(str(family) for family in card.get("mechanic_families", [])),
    ]
    return " ".join(str(part).lower() for part in parts if part is not None)
```

- [ ] **Step 4: Run surface-intent tests**

Run:

```powershell
pytest tests/test_surface_intent.py -q
```

Expected: PASS.

- [ ] **Step 5: Run config-quality tests that consume surface intent**

Run:

```powershell
pytest tests/test_config_quality_contract.py tests/test_configure_handoff_contract.py -q
```

Expected: PASS. Existing fallback diagnostics must still work for genuinely unknown cards, but the ShadowPriest-specific card identities must no longer project as generic fallback.

- [ ] **Step 6: Commit surface-intent projection**

```powershell
git add src/hsconfig/surface_intent.py tests/test_surface_intent.py
git commit -m "feat: project specific card surface intents"
```

Expected: one commit with projection code and tests.

---

### Task 4: Add ShadowPriest Strong Package Regression

**Files:**
- Modify: `tests/test_shadowpriest_e2e.py`

**Interfaces:**
- Consumes: `hsconfig.cli.main()`.
- Consumes: `build_config_quality_report(package: Path) -> dict`.
- Produces: a real ShadowPriest strong-fixture regression that protects this exact audit finding.

- [ ] **Step 1: Add failing E2E regression**

Append this code to `tests/test_shadowpriest_e2e.py`:

```python

def test_source_backed_strong_shadowpriest_has_no_known_semantic_intent_fallbacks(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
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
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
        ]
    )

    reports = out / "reports"
    behavior_report = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    surface_intent = json.loads(
        (reports / "surface_intent.json").read_text(encoding="utf-8")
    )
    quality = build_config_quality_report(out)

    known_cards = {
        "DS1_233",
        "GVG_009",
        "NX2_019",
        "SCH_514",
        "SW_446",
        "TOY_381",
        "VAC_419",
        "VAC_512",
        "YOD_032",
    }
    semantic_default_rows = [
        {
            "card_id": row.get("card_id"),
            "behavior_block": row.get("behavior_block"),
            "intent": row.get("intent"),
            "reason": row.get("semantic_score", {}).get("reason"),
        }
        for row in behavior_report["rows"]
        if row.get("card_id") in known_cards
        and row.get("semantic_score", {}).get("reason") == "semantic_default"
    ]
    fallback_surface_rows = [
        {
            "card_id": row.get("card_id"),
            "surface": row.get("surface"),
            "intent": row.get("intent"),
            "intent_source": row.get("intent_source"),
        }
        for row in surface_intent["rows"]
        if row.get("card_id") in known_cards
        and row.get("intent_source") == "fallback"
    ]

    assert code == 0
    assert semantic_default_rows == []
    assert fallback_surface_rows == []
    assert quality["authority"] == "diagnostic_only"
    assert quality["apply_blocking"] is False
    assert quality["checks"]["card_behavior"]["semantic_default_rows"] == []
```

- [ ] **Step 2: Run this E2E test and verify it fails before Task 2/3 code**

Run:

```powershell
pytest tests/test_shadowpriest_e2e.py::test_source_backed_strong_shadowpriest_has_no_known_semantic_intent_fallbacks -q
```

Expected before implementation: FAIL with visible rows for `GVG_009`, `SCH_514`, `VAC_419`, `VAC_512`, `YOD_032`, and surface fallback rows.

- [ ] **Step 3: Run this E2E test after Task 2/3 implementation**

Run:

```powershell
pytest tests/test_shadowpriest_e2e.py::test_source_backed_strong_shadowpriest_has_no_known_semantic_intent_fallbacks -q
```

Expected after implementation: PASS.

- [ ] **Step 4: Run existing ShadowPriest E2E coverage**

Run:

```powershell
pytest tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_shadowpriest_fresh_closure_proof.py -q
```

Expected: PASS. Darkbishop remains effect-visible but absent from Mulligan keeps. `Combo.json` remains suppressed unless exact ordered combo evidence exists.

- [ ] **Step 5: Commit ShadowPriest E2E regression**

```powershell
git add tests/test_shadowpriest_e2e.py
git commit -m "test: guard shadowpriest semantic intent coverage"
```

Expected: one commit containing the E2E regression.

---

### Task 5: Document Diagnostic Intent Boundary

**Files:**
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`

**Interfaces:**
- Consumes: taxonomy reasons from Task 2.
- Produces: operator-facing skill reference that explains the scoring boundary without implying new runtime authority.

- [ ] **Step 1: Add policy text**

In `.agents/skills/hsconfig/references/card-behavior-policy.md`, insert this section before `## Choice Surface Lowering`:

```markdown
## Diagnostic Intent Taxonomy

Card intent taxonomy is diagnostic and scoring-only. It may choose stronger
values for supported per-card CardID behavior rows, but it must not create a new
runtime surface, a new apply gate, or unsupported HearthRanger syntax.

Known ShadowPriest-style semantics that should not remain generic defaults when
card text or exact card identity is available:

- Direct enemy hero burn, for example Mind Blast.
- Conditional minion-death burn, for example Mind Sear.
- Reciprocal hero burn, for example Shadowbomber and Acupuncture.
- Damage-aura amplification, for example Voidtouched Attendant.
- Self-damage resource/refill, for example Raise Dead.
- Self-damage liability body, for example Brain Masseuse.
- Opponent-damage discount tempo, for example Frenzied Felwing.
- Hero-power cost aura, for example Papercraft Angel.
- Hero-power transform, for example Darkbishop Benedictus.
- Location tempo/draw, for example Cathedral of Atonement.

These classifications explain `semantic_score.reason` and `surface_intent`
rows. They do not prove Mulligan keeps, exact combo order, targeting conditions,
or post-game tuning. Keep unsupported sequencing and timing claims report-only
unless a documented VisionAI surface can express them safely.
```

- [ ] **Step 2: Run docs policy tests**

Run:

```powershell
pytest tests/test_operator_docs_contract_policy.py tests/test_skill_contract_entrypoint.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit documentation**

```powershell
git add .agents/skills/hsconfig/references/card-behavior-policy.md
git commit -m "docs: clarify diagnostic card intent taxonomy"
```

Expected: one commit containing only the policy reference update.

---

### Task 6: Final Verification With Fresh ShadowPriest Package

**Files:**
- No source edits in this task.
- Generated outputs under a temporary or ignored output directory only.

**Interfaces:**
- Consumes: completed Tasks 1-5.
- Produces: verified currentness, package validity, no known ShadowPriest semantic fallback debt, clean worktree.

- [ ] **Step 1: Refresh repo state**

Run:

```powershell
git fetch --all --prune --tags
python scripts/check_hsconfig_currentness.py --cwd . --json
git status --short --branch
```

Expected:

- Fetch exits 0.
- Currentness JSON reports clean for runtime work and not behind upstream.
- `git status --short --branch` shows the current feature branch and no unstaged/untracked source changes except intentional committed work.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
pytest tests/test_card_intent_taxonomy.py tests/test_semantic_intent_score.py tests/test_surface_intent.py tests/test_shadowpriest_e2e.py -q
```

Expected: PASS.

- [ ] **Step 3: Run contract and guardrail tests**

Run:

```powershell
pytest tests/test_card_behavior_router.py tests/test_config_quality_contract.py tests/test_configure_handoff_contract.py tests/test_contract_preflight.py tests/test_contract_doctor.py tests/test_no_second_gate_contract.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full suite**

Run:

```powershell
pytest -q
```

Expected: PASS with the repo's existing skipped-test count.

- [ ] **Step 5: Generate a fresh ShadowPriest package without touching real runtime**

Run:

```powershell
$out = "outputs\verification-shadowpriest-semantic-intent"
Remove-Item -LiteralPath $out -Recurse -Force -ErrorAction SilentlyContinue
python -m hsconfig.cli prepare --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "$env:TEMP\hsconfig-shadowpriest-runtime" --out $out --source-documents-json "tests/fixtures/source_documents_shadowpriest_strong.json" --json
python -m hsconfig.cli validate --package "$out" --json
python -m hsconfig.cli contract-preflight --package "$out" --json
python -m hsconfig.cli contract-doctor --package "$out" --json
```

Expected:

- `prepare` exits 0.
- `validate` reports `status=passed`.
- `contract-preflight` keeps package apply readiness tied to `reports/operator_summary.json`.
- `contract-doctor` shows no semantic-default rows for known ShadowPriest cards and no fallback surface-intent rows for known ShadowPriest mechanics.

- [ ] **Step 6: Inspect generated reports with a compact assertion**

Run:

```powershell
$out = "outputs\verification-shadowpriest-semantic-intent"
$behavior = Get-Content -LiteralPath "$out\reports\card_behavior_plan_report.json" -Raw | ConvertFrom-Json
$surface = Get-Content -LiteralPath "$out\reports\surface_intent.json" -Raw | ConvertFrom-Json
$op = Get-Content -LiteralPath "$out\reports\operator_summary.json" -Raw | ConvertFrom-Json
$known = @("DS1_233","GVG_009","NX2_019","SCH_514","SW_446","TOY_381","VAC_419","VAC_512","YOD_032")
$semanticDefaults = @($behavior.rows | Where-Object { $known -contains $_.card_id -and $_.semantic_score.reason -eq "semantic_default" })
$fallbacks = @($surface.rows | Where-Object { $known -contains $_.card_id -and $_.intent_source -eq "fallback" })
[pscustomobject]@{
  technical_status = $op.technical_status
  semantic_status = $op.semantic_status
  runtime_apply_allowed = $op.runtime_apply_allowed
  default_only_runtime_surfaces = @($op.default_only_runtime_surfaces)
  known_semantic_default_rows = $semanticDefaults.Count
  known_surface_intent_fallback_rows = $fallbacks.Count
} | ConvertTo-Json -Depth 4
```

Expected JSON:

```json
{
  "technical_status": "VALID_PACKAGE",
  "semantic_status": "SOURCE_BACKED_STRONG",
  "runtime_apply_allowed": true,
  "default_only_runtime_surfaces": [],
  "known_semantic_default_rows": 0,
  "known_surface_intent_fallback_rows": 0
}
```

- [ ] **Step 7: Remove verification output if it is not ignored**

Run:

```powershell
git status --short outputs\verification-shadowpriest-semantic-intent
```

If the command prints untracked files, remove the verification output:

```powershell
Remove-Item -LiteralPath "outputs\verification-shadowpriest-semantic-intent" -Recurse -Force
```

Expected: no generated verification package remains as an untracked source artifact unless the repo already ignores it.

- [ ] **Step 8: Final clean status**

Run:

```powershell
git status --short --branch
```

Expected: clean worktree on the implementation branch.

---

## Self-Review

- Spec coverage: The plan addresses the audit finding directly: current ShadowPriest config is usable, but several known cards still project generic semantic/default intent. Tasks 1-4 make those exact cards source-backed and test-covered without changing runtime authority. Task 5 records the boundary in the skill reference. Task 6 verifies currentness, tests, fresh package behavior, and clean worktree.
- Placeholder scan: This plan contains exact file paths, exact function names, exact test code, exact implementation snippets, exact commands, and expected outputs. It intentionally contains no open-ended implementation steps.
- Type consistency: New taxonomy reason strings are introduced in Task 1, returned by `classify_card_intent()` in Task 2, projected by `build_surface_intent()` in Task 3, and asserted against generated package reports in Task 4 and Task 6.
- Scope boundary: No HSTuner, no replay/log logic, no new runtime surfaces, no new apply gate, and no manual ShadowPriest runtime patching.

# HSConfig Source Contract Opening-Hand Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the last narrow source-contract gap so explicit opening-hand source evidence can be represented without reintroducing default-only output or the Darkbishop Benedictus mulligan bug.

**Architecture:** Keep HSConfig's existing no-block runtime contract: valid decks still produce load-safe configs even when public source depth is partial. `SOURCE_BACKED_STRONG` remains an evidence-quality label, not a runtime-write gate. The only behavioral change is inside source-claim compilation: Start-of-Game / hero-power effect cards are not inferred as mulligan keeps from effect text, but they may produce `mulligan_keep` when the source sentence directly says to keep that exact card in the mulligan or opening hand.

**Tech Stack:** Python, pytest, existing HSConfig source acquisition / claim compiler / operator summary pipeline, existing docs under `docs/operator`.

## Global Constraints

- Work in `C:\Users\darbo\Documents\HSConfig`.
- Do not modify HSranger files under `C:\Users\darbo\Documents\HS` for this task.
- Do not add new runtime surfaces.
- Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.
- Do not make `SOURCE_BACKED_STRONG` a runtime-write gate.
- Do not promote decklists, stats pages, snippets, default runtime, or policy fallback to `SOURCE_BACKED_STRONG`.
- Preserve the Darkbishop boundary: keep `SW_448` / Mind Spike / `hero_power_transform` effect semantics, but never infer a Darkbishop mulligan keep from Start-of-Game or Hero Power text alone.
- Any valid deck in the universal Wild matrix must still produce a `VALID_PACKAGE` with `runtime_load_safe=true` and `runtime_apply_mode=load_safe_apply`.

---

## File Structure

- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_claim_compiler.py`
  - Responsibility: Extract source claims from acquired public/static source records.
  - Planned change: Add a helper that distinguishes direct card-specific keep wording from a sentence that merely mentions a Start-of-Game / hero-power effect card near another keep.

- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_claim_compiler.py`
  - Responsibility: Unit tests for claim extraction.
  - Planned change: Add one positive test for an explicit opening-hand keep of a Start-of-Game card and one negative test for same-sentence incidental Darkbishop mention.

- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`
  - Responsibility: Operator-facing source-strength contract.
  - Planned change: Clarify the exact compiler rule and add CuteWarrior to the source-depth snapshot as `SOURCE_BACKED_PARTIAL`, not Strong.

- Optional Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\universal-wild-no-block-contract.md`
  - Responsibility: No-block runtime contract and proof matrix.
  - Planned change: Only edit if the proof matrix wording needs to mention that Strong evidence and no-block runtime are separate for the new explicit-opening-hand edge case.

---

### Task 1: Add Source-Claim Compiler Regression Tests

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\tests\test_source_claim_compiler.py`

**Interfaces:**
- Consumes: `compile_source_search_records(deck_name, deck_identity, acquired_records, current_date)`
- Produces: Two failing tests that describe the exact desired compiler behavior before implementation.

- [ ] **Step 1: Open the current compiler tests**

Run:

```powershell
Select-String -Path 'C:\Users\darbo\Documents\HSConfig\tests\test_source_claim_compiler.py' -Pattern 'test_compiler_does_not_turn_key_effect_text_into_mulligan_keep' -Context 5,60
```

Expected: The existing Darkbishop negative regression test is visible.

- [ ] **Step 2: Add the positive explicit-opening-hand test**

Append this test directly after `test_compiler_does_not_turn_key_effect_text_into_mulligan_keep`:

```python
def test_compiler_allows_explicit_opening_hand_keep_for_start_of_game_card():
    deck_identity = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "cost": 5,
                "count": 1,
                "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
            },
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        ]
    }
    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        acquired_records=[
            {
                "source_family": "guide",
                "source_visibility": "full_text",
                "source_record_strength": "candidate_strong",
                "source_title": "Shadow Priest Guide 2026",
                "source_url": "https://example.test/shadow-explicit-keep",
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "TOY_381"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "normalized_text": (
                    "Mulligan: keep Darkbishop Benedictus in your opening hand when this guide "
                    "explicitly calls for the card. Darkbishop Benedictus changes your hero power "
                    "to Mind Spike."
                ),
            }
        ],
        current_date="2026-07-15",
    )

    claims = [claim for record in payload["records"] for claim in record["claims"]]
    keep_ids = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "mulligan_keep"
        for card_id in claim["cards"]
    }
    transform_ids = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "hero_power_transform"
        for card_id in claim["cards"]
    }

    assert keep_ids == {"SW_448"}
    assert transform_ids == {"SW_448"}
```

- [ ] **Step 3: Add the incidental-mention negative test**

Append this test after the positive test:

```python
def test_compiler_does_not_keep_start_of_game_card_from_incidental_keep_sentence():
    deck_identity = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "cost": 5,
                "count": 1,
                "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
            },
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        ]
    }
    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        acquired_records=[
            {
                "source_family": "guide",
                "source_visibility": "full_text",
                "source_record_strength": "candidate_strong",
                "source_title": "Shadow Priest Guide 2026",
                "source_url": "https://example.test/shadow-incidental-effect",
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "TOY_381"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "normalized_text": (
                    "Mulligan: keep Papercraft Angel while Darkbishop Benedictus enables the "
                    "Shadow hero power and Mind Spike."
                ),
            }
        ],
        current_date="2026-07-15",
    )

    claims = [claim for record in payload["records"] for claim in record["claims"]]
    keep_ids = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "mulligan_keep"
        for card_id in claim["cards"]
    }
    transform_ids = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "hero_power_transform"
        for card_id in claim["cards"]
    }

    assert keep_ids == {"TOY_381"}
    assert transform_ids == {"SW_448"}
```

- [ ] **Step 4: Run the focused tests and verify the positive test fails**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_claim_compiler.py::test_compiler_allows_explicit_opening_hand_keep_for_start_of_game_card tests\test_source_claim_compiler.py::test_compiler_does_not_keep_start_of_game_card_from_incidental_keep_sentence -q
```

Expected before implementation: The explicit-opening-hand test fails because `SW_448` is filtered out of `mulligan_keep`. The incidental negative test may already pass.

- [ ] **Step 5: Do not commit yet**

Expected: Tests are written and at least one new test proves the bug.

---

### Task 2: Implement Direct Keep-Intent Detection

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_claim_compiler.py`

**Interfaces:**
- Consumes: `_positive_keep_sentences(text) -> list[str]`, `_is_non_opening_hand_effect_card(card) -> bool`
- Produces: `_sentence_directly_keeps_card(lowered_sentence: str, card_name: str) -> bool`

- [ ] **Step 1: Locate `_explicit_keep_rows`**

Run:

```powershell
Select-String -Path 'C:\Users\darbo\Documents\HSConfig\src\hsconfig\source_claim_compiler.py' -Pattern 'def _explicit_keep_rows' -Context 0,35
```

Expected: The function contains `and not _is_non_opening_hand_effect_card(card)`.

- [ ] **Step 2: Add a helper for direct keep wording**

Add this helper above `_explicit_keep_rows`:

```python
def _sentence_directly_keeps_card(lowered_sentence: str, card_name: str) -> bool:
    normalized_sentence = " ".join(lowered_sentence.split())
    normalized_name = card_name.lower()
    keep_before_name = (
        f"keep {normalized_name}" in normalized_sentence
        or f"keep the {normalized_name}" in normalized_sentence
        or f"keep your {normalized_name}" in normalized_sentence
    )
    name_before_keep = (
        f"{normalized_name} is a keep" in normalized_sentence
        or f"{normalized_name} is an auto keep" in normalized_sentence
        or f"{normalized_name} should be kept" in normalized_sentence
        or f"{normalized_name} can be kept" in normalized_sentence
    )
    return keep_before_name or name_before_keep
```

- [ ] **Step 3: Replace the non-opening-hand filter in `_explicit_keep_rows`**

Change the condition inside `_explicit_keep_rows` from:

```python
                and not _is_non_opening_hand_effect_card(card)
```

to:

```python
                and (
                    not _is_non_opening_hand_effect_card(card)
                    or _sentence_directly_keeps_card(lowered_sentence, name)
                )
```

The final condition should read:

```python
            if (
                name
                and card_id
                and name.lower() in lowered_sentence
                and (
                    not _is_non_opening_hand_effect_card(card)
                    or _sentence_directly_keeps_card(lowered_sentence, name)
                )
                and card_id not in seen
            ):
```

- [ ] **Step 4: Run the two new focused tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_claim_compiler.py::test_compiler_allows_explicit_opening_hand_keep_for_start_of_game_card tests\test_source_claim_compiler.py::test_compiler_does_not_keep_start_of_game_card_from_incidental_keep_sentence -q
```

Expected: `2 passed`.

- [ ] **Step 5: Run all source-claim compiler tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_claim_compiler.py -q
```

Expected: All tests in `tests\test_source_claim_compiler.py` pass.

- [ ] **Step 6: Do not commit yet**

Expected: Implementation is minimal and scoped to compiler behavior.

---

### Task 3: Verify ShadowPriest and Universal No-Block Behavior

**Files:**
- Test only: `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_depth_e2e.py`
- Test only: `C:\Users\darbo\Documents\HSConfig\tests\test_shadowpriest_fresh_closure_proof.py`
- Test only: `C:\Users\darbo\Documents\HSConfig\tests\test_universal_wild_no_block_matrix.py`
- Test only: `C:\Users\darbo\Documents\HSConfig\tests\test_lean_source_backed_strong_autopilot.py`

**Interfaces:**
- Consumes: Existing generated-package assertions.
- Produces: Evidence that the current ShadowPriest package still keeps the effect contract but does not default Darkbishop into `Mulligan.json`, and that all 12 Wild decks remain load-safe.

- [ ] **Step 1: Run ShadowPriest regressions**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_shadowpriest_depth_e2e.py tests\test_shadowpriest_fresh_closure_proof.py -q
```

Expected: All selected ShadowPriest tests pass.

- [ ] **Step 2: Run no-block and Strong-closure tests**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_universal_wild_no_block_matrix.py tests\test_lean_source_backed_strong_autopilot.py tests\test_source_acquisition.py tests\test_source_acquisition_strong_closure.py tests\test_source_autopilot.py tests\test_strong_closure_profiles.py -q
```

Expected: All selected tests pass. Any failure that changes `runtime_apply_mode`, `default_only_runtime_surfaces`, or Darkbishop keep behavior must be fixed before continuing.

- [ ] **Step 3: Inspect the current git diff**

Run:

```powershell
git diff -- src\hsconfig\source_claim_compiler.py tests\test_source_claim_compiler.py
```

Expected: Diff shows only the helper, the `_explicit_keep_rows` condition, and the two tests.

- [ ] **Step 4: Do not commit yet**

Expected: Code behavior is proven before documentation is touched.

---

### Task 4: Update Operator Contract Wording

**Files:**
- Modify: `C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md`

**Interfaces:**
- Consumes: The compiler rule from Task 2.
- Produces: Operator-facing wording that matches the implementation and prevents future reintroduction of the Darkbishop keep bug.

- [ ] **Step 1: Locate the Darkbishop boundary section**

Run:

```powershell
Select-String -Path 'C:\Users\darbo\Documents\HSConfig\docs\operator\source-backed-strong-closure.md' -Pattern 'Darkbishop Benedictus is the canonical boundary case' -Context 0,12
```

Expected: The section describing `hero_power_transform`, Mind Spike, and no inferred keep is visible.

- [ ] **Step 2: Replace the boundary paragraph with exact compiler wording**

Replace the current Darkbishop paragraph with:

```markdown
Darkbishop Benedictus is the canonical boundary case: preserve the start-of-game
`hero_power_transform`, Mind Spike, and Shadow runtime effect in contract/CardID
semantics, but never infer an opening-hand keep from Start-of-Game, Shadowform,
or Hero Power text alone. A `mulligan_keep` row for a Start-of-Game or
hero-power-transform card is valid only when the same public guide sentence
directly says to keep that exact card in the mulligan or opening hand.
Incidental mentions such as "keep Papercraft Angel while Darkbishop enables the
Shadow hero power" must keep Papercraft only and preserve Darkbishop as effect
semantics.
```

- [ ] **Step 3: Add CuteWarrior to the current blocker snapshot if missing**

If `CuteWarrior` is absent from the snapshot table, add this row after `PirateDH`:

```markdown
| CuteWarrior | `SOURCE_BACKED_PARTIAL` | current full-text mulligan/gameplan source needed before partial warrior-specific rows can count as strong evidence | `add_current_full_text_mulligan_or_gameplan_source` |
```

Expected: The 12-deck source-depth discussion matches the universal Wild matrix without pretending CuteWarrior is Strong.

- [ ] **Step 4: Run markdown grep sanity checks**

Run:

```powershell
Select-String -Path 'docs\operator\source-backed-strong-closure.md' -Pattern 'directly says to keep that exact card|CuteWarrior|SOURCE_BACKED_STRONG is an evidence-quality label'
```

Expected: All three patterns appear.

- [ ] **Step 5: Do not commit yet**

Expected: Documentation now matches the compiler behavior.

---

### Task 5: Full Targeted Verification and Commit

**Files:**
- Verify: all files changed in Tasks 1-4.

**Interfaces:**
- Consumes: Completed compiler and documentation changes.
- Produces: A clean, committed implementation ready for the next `hsconfig configure` / ShadowPriest rebuild.

- [ ] **Step 1: Run the targeted source-contract suite**

Run:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_claim_compiler.py tests\test_universal_wild_no_block_matrix.py tests\test_lean_source_backed_strong_autopilot.py tests\test_source_acquisition.py tests\test_source_acquisition_strong_closure.py tests\test_source_autopilot.py tests\test_shadowpriest_depth_e2e.py tests\test_shadowpriest_fresh_closure_proof.py tests\test_strong_closure_profiles.py -q
```

Expected: All selected tests pass. The previous baseline was `99 passed`; after adding two tests, expect `101 passed` if no selected-test count changed.

- [ ] **Step 2: Rebuild a ShadowPriest package in dry-run / normal generated-artifact mode if the CLI supports it without runtime apply**

Run:

```powershell
python -m hsconfig configure --deck-name ShadowPriest --deck-code 'AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=' --hsid 2737726722 --hdt-deck-id c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602 --online-source --auto-source --json
```

Expected: Command returns JSON with a valid package status. If this CLI form requires a different local flag, inspect `python -m hsconfig --help` and use the existing normal non-apply configure command. Do not use a runtime apply command in this task.

- [ ] **Step 3: Verify generated ShadowPriest semantics if artifacts were produced**

Run the repository's existing artifact inspection command or open the generated package path reported by Step 2. Check:

```text
Mulligan.json does not default-keep SW_448.
SW_448.json or the equivalent CardID runtime file still contains the hero-power / Mind Spike / Shadowform effect semantics.
reports/operator_summary.json has default_only_runtime_surfaces empty.
reports/operator_summary.json remains the apply authority.
```

Expected: Effect preserved, no default Darkbishop keep, no default-only runtime surfaces.

- [ ] **Step 4: Inspect final diff**

Run:

```powershell
git diff -- src\hsconfig\source_claim_compiler.py tests\test_source_claim_compiler.py docs\operator\source-backed-strong-closure.md
git status --short --branch
```

Expected: Only the planned files changed. No runtime evidence, logs, caches, or generated private artifacts are staged.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src\hsconfig\source_claim_compiler.py tests\test_source_claim_compiler.py docs\operator\source-backed-strong-closure.md
git commit -m "fix: preserve explicit opening-hand source claims"
```

Expected: Commit succeeds.

---

## Self-Review Checklist

- [ ] The plan keeps HSConfig autonomous: valid decks still get load-safe configs when public source coverage is partial.
- [ ] The plan keeps `SOURCE_BACKED_STRONG` honest: no decklist/stat/snippet/default/policy fallback promotion.
- [ ] The plan prevents hidden default-only output: runtime surfaces must be emitted, suppressed with reason, or reported as gaps.
- [ ] The plan preserves Darkbishop effect semantics while preventing default mulligan keep inference.
- [ ] The plan allows explicit opening-hand source evidence for Start-of-Game cards only when the same source sentence directly keeps that exact card.
- [ ] The plan does not introduce Presume/Concede output.
- [ ] The plan uses focused tests before implementation and targeted regression tests after implementation.
- [ ] The plan does not require new dependencies or a broad architecture rewrite.

## Task 4 Report: Update 11-Deck Matrix Expectations

Status: DONE

### Scope completed

- Updated `docs/operator/archetype-fixture-matrix.json` only for the 11 representative deck rows.
- Added `closure_profile`, `closure_profile_required_claims`, and `closure_profile_first_missing_link` to every row.
- Preserved all existing `expected_semantic_status` values and partial-deck `first_missing_source_action` values.
- Added the requested matrix assertions in:
  - `tests/test_universal_wild_no_block_matrix.py`
  - `tests/test_no_default_only_semantic_archetype_matrix.py`

### Exact matrix closure mapping

| Deck | Closure profile | First missing link |
| --- | --- | --- |
| ShadowPriest | `aggro_burn_hero_power` | `none` |
| CtAPaladin | `board_flood_recruit` | `missing_claim_group:mulligan_keep|mulligan_discard|card_role` |
| PirateRogue | `weapon_pressure` | `none` |
| BigShaman | `board_flood_recruit` | `none` |
| Discolock | `combo_setup` | `missing_claim_group:mulligan_keep|mulligan_discard|card_role` |
| TreantDruid | `board_flood_recruit` | `missing_claim_group:mulligan_keep|mulligan_discard|card_role` |
| ImbueMage | `aggro_burn_hero_power` | `none` |
| MechPala | `board_flood_recruit` | `none` |
| Kingslayer | `weapon_pressure` | `missing_claim_group:mulligan_keep|mulligan_discard|card_role` |
| Boarlock | `combo_setup` | `missing_claim_group:combo_sequence|card_role` |
| PirateDH | `weapon_pressure` | `missing_claim_group:mulligan_keep|mulligan_discard|card_role` |

`closure_profile_required_claims` mirrors the corresponding `PROFILE_REQUIREMENTS` claim-group alternatives in `src/hsconfig/strong_closure_profiles.py` without modifying that model.

### Test evidence

1. RED test run:
   `python -m pytest tests/test_universal_wild_no_block_matrix.py::test_every_matrix_deck_declares_closure_profile -q`
   Result: failed as expected with `KeyError: 'closure_profile'` before the matrix fields were added.
2. Required verification:
   `python -m pytest tests/test_universal_wild_no_block_matrix.py tests/test_no_default_only_semantic_archetype_matrix.py -q`
   Result: passed.
3. Matrix integrity check: JSON parsed successfully; exact mappings were checked across all 11 deck rows; `git diff --check` completed without whitespace errors.

### Constraints preserved

- No runtime, replay, winrate, HSTuner, or post-game logic changed.
- `operator_summary.json` remains untouched as normal apply authority.
- No promotion policy, source schema, runtime surface generation, or Darkbishop/Mulligan semantics changed.
- No legacy normal-output surfaces were added.

### Commit

`da02ebb docs: expose closure profiles in archetype matrix`

---

## Task 4 Follow-up: Wire Text Claims Into Source Autopilot

### Result

Implemented the narrow source-autopilot integration on branch `codex/hsconfig-source-backed-strong-autopilot`.

### Red Evidence

Added `test_autopilot_extracts_full_text_claims_before_closure_evaluation` first, then ran:

```text
python -m pytest -p no:cacheprovider tests\test_source_autopilot.py::test_autopilot_extracts_full_text_claims_before_closure_evaluation -q
```

Expected failure observed before implementation:

```text
1 failed
AssertionError: assert ('mulligan_keep', ('TOY_381',)) in set()
```

The failure showed that `build_source_autopilot_bundle` produced no text-derived evidence rows before the integration.

### Green Evidence

After implementation, the focused autopilot test and configure-level ShadowPriest regression passed:

```text
2 passed in 1.83s
```

The configure regression inspected `03_source_autopilot/source_documents.json` and verified that `SW_448` has a `hero_power_transform` claim and no `mulligan_keep` claim.

The required full command was also run:

```text
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py tests\test_source_autopilot.py tests\test_configure_online_source.py -q
```

Result: `42 passed, 2 failed`.

The two failures are existing ShadowPriest closure expectations in `tests/test_source_autopilot.py` (`test_build_source_autopilot_bundle_outputs_strict_source_documents` and `test_source_autopilot_does_not_require_extra_non_mulligan_surface_when_profile_closed`). The fixture has no `normalized_text` and no `source_record_strength`, so current source policy marks it non-promotable with `missing_acquired_source_text`, `non_promoting_source_record`, and `promotion_explicitly_disabled`. The new extractor returns no text claims for that fixture; changing source trust or unrelated fixture policy was outside this task.

### Changed Files

- `src/hsconfig/source_autopilot.py`: imports `extract_text_claims` and appends deduplicated text claims after structured mulligan rows and before explicit claims.
- `tests/test_source_autopilot.py`: adds the full-text claim integration test covering Papercraft keep, SW_448 discard, SW_448 hero-power transform, and no SW_448 mulligan keep.
- `tests/test_configure_online_source.py`: checks generated source documents for the ShadowPriest claim-kind separation.

### Commit

`4c9d75586eb72466d9f64a1adeb5a544d098175d` (`feat: feed full text claims into source autopilot`)

### Concerns

The requested suite is not fully green because of the two fixture/promotion-state failures described above. No source trust was broadened, and no runtime writers, extractor implementation, unrelated tests, or unrelated contributor changes were modified.

---

## Task 4 Fix: Align ShadowPriest Fixture With Strong Evidence Policy

### Root Cause

The ShadowPriest source-search fixture declared `source_visibility: full_text` and included explicit claims, but it did not contain acquired guide body text (`normalized_text` or `text`) and did not declare `source_record_strength: candidate_strong`. Task 2/3 source policy therefore correctly classified the record as partial and prevented `SOURCE_BACKED_STRONG` closure. The failure was fixture drift, not a source-autopilot trust or behavior defect.

### Fix

Updated `tests/fixtures/source_search_shadowpriest_2026.json` only. The guide record now declares `source_record_strength: candidate_strong` and includes concise normalized public-guide text covering the aggressive burn posture, mulligan guidance, Darkbishop Benedictus's start-of-game Shadowform/Mind Spike semantics, and cheap pressure card roles. The body explicitly avoids treating Darkbishop Benedictus as an opening-hand keep.

### Test Evidence

Targeted regressions:

```text
python -m pytest -p no:cacheprovider tests\test_source_autopilot.py::test_build_source_autopilot_bundle_outputs_strict_source_documents tests\test_source_autopilot.py::test_source_autopilot_does_not_require_extra_non_mulligan_surface_when_profile_closed -q
```

Result: `2 passed in 0.24s`.

Required Task 4 suite:

```text
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py tests\test_source_autopilot.py tests\test_configure_online_source.py -q
```

Result: `44 passed in 7.88s`.

### Commit

Commit SHA: `e8dd846d780fe4759de9dcf66877b4c340647e77` (`test: align shadowpriest source fixture with strong evidence policy`).

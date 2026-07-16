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

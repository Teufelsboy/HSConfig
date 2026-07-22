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

---

## Semantic Intent Scoring SDD Task 4: Runtime JSON Cleanliness

Status: DONE

### Scope completed

- Added a compiler regression in `tests/test_compile_cardid.py`.
- The fixture behavior row includes diagnostic-only `semantic_score` metadata with:
  - `band: high`
  - `reason: conditional_minion_death_burn`
  - `profile: source_claim`
  - `matched_signals: [enemy_hero_damage, death_condition]`
- Verified `compile_cardid_behaviors(..., rows=[...])` emits `NX2_019.json` runtime rows with only `comment`, `condition`, and `value`.

### Test evidence

```text
python -m pytest tests\test_compile_cardid.py -q -p no:cacheprovider
13 passed in 0.15s
```

### Compiler boundary

`src/hsconfig/compile_cardid.py` was not changed. The existing compiler path already renders explicit behavior rows through the lean runtime row shape and does not leak `semantic_score`.

---

## Configure Acceptance Summary Boundary Sentinel

Status: DONE

### Changed files

- `tests/test_configure_cli.py`

### RED / Sentinel result

- Command: `pytest tests\test_configure_cli.py::test_acceptance_summary_helper_stays_configure_local_projection -q`
- Result before final alignment: `1 failed`
- Expected sentinel failure: the temporary assertion expected `_build_acceptance_summary` in `src/hsconfig/commands/apply.py`; the failure confirmed the new boundary test detects whether the helper crosses into apply code.

### GREEN / Verification

- Command: `pytest tests\test_configure_cli.py::test_build_acceptance_summary_surfaces_diagnostics_without_blocking tests\test_configure_cli.py::test_acceptance_summary_helper_stays_configure_local_projection tests\test_configure_cli.py::test_configure_writes_diagnostic_config_quality_summary tests\test_configure_cli.py::test_configure_quality_summary_failure_stays_diagnostic_only -q`
- Result: `4 passed in 6.87s`
- Post-commit command: `pytest tests\test_configure_cli.py -q`
- Result: `16 passed in 7.46s`

### Commit

- `968c0fe692a46f62da94b79fbe059a07aefaac6c` (`test: guard configure acceptance summary boundary`)

### Notes / risks

- `acceptance_summary` remains top-level in `configure_summary.json` and absent from `reports/operator_summary.json`.
- `reports/operator_summary.json` remains the normal apply authority.
- `SOURCE_BACKED_STRONG`, `source_status_apply_blocking=false`, `default_only_runtime_surfaces`, and `config_quality_summary` are covered as diagnostic-only for load-safe usability in the helper regression.
- No product logic, operator-summary schema, new reports, HSTuner path, runtime artifacts, or runtime behavior were changed.
- Pre-existing dirty files `.superpowers/sdd/progress.md` and `.superpowers/sdd/task-3-report.md` were not touched or staged.

---

# Task 4 Report: Source Freshness Provenance Normalizer

## Scope

Implemented Task 4 only in the authorized HSConfig files. The change projects
Task 3 freshness diagnostics through the research-result contract sentinel and
contract preflight. It remains diagnostic-only; `reports/operator_summary.json`
remains the only normal apply authority.

## TDD Evidence

1. Added `test_sentinel_counts_missing_freshness_without_apply_blocking`.
2. Added `test_contract_preflight_exposes_research_freshness_missing_count`.
3. RED command:

   ```powershell
   python -m pytest tests/test_research_result_contract_sentinel.py::test_sentinel_counts_missing_freshness_without_apply_blocking tests/test_contract_preflight.py::test_contract_preflight_exposes_research_freshness_missing_count -q
   ```

   Result: `2 failed`. Each failure was the expected absent field:
   `summary.freshness_missing_count` and
   `research_context.latest_research_result_contract_freshness_missing_count`.

4. GREEN command: same targeted command.

   Result: `2 passed in 3.71s`.

5. Required full target command:

   ```powershell
   python -m pytest tests/test_research_result_contract_sentinel.py tests/test_contract_preflight.py -q
   ```

   Result: `28 passed in 7.47s`.

## Changed Files

- `src/hsconfig/research_result_contract_sentinel.py`
  - Adds per-row `freshness_status`, `current_or_evergreen`, and
    `current_or_evergreen_reason` from strict validation.
  - Adds summary `freshness_missing_count` and `current_or_evergreen_count`.
- `src/hsconfig/contract_preflight.py`
  - Projects freshness-missing count into `ResearchContextPreflight`.
  - Returns zero for not-found, incomplete, and sentinel-exception fallbacks.
- `src/hsconfig/commands/contract_preflight.py`
  - Mirrors the zero fallback in the unavailable research-context payload.
- `tests/test_research_result_contract_sentinel.py`
  - Covers missing freshness reporting and updates the exact summary contract.
- `tests/test_contract_preflight.py`
  - Covers the preflight research-context projection.
- `.superpowers/sdd/task-4-report.md`
  - Records Task 4 implementation and verification evidence.

## Self-Review

- `source_status_apply_blocking` remains `False` in the sentinel, preflight
  payload, and unavailable fallback; freshness gaps are not apply authority.
- `reports/operator_summary.json` remains the normal runtime apply authority.
- No runtime apply/write, HSTuner, logs, online research, dependencies, or
  runtime surfaces were added or changed.
- No Darkbishop Benedictus or Mulligan behavior was touched.
- `git diff --check` completed with exit code 0 before commit.

## Commit

- Message: `feat: report research provenance gaps`
- Scope: the six Task 4 authorized files listed above.

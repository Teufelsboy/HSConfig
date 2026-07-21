# Task 3 Report: Semantic Scoring In Card Behavior Routing

Status: done

Files changed:
- `src/hsconfig/card_behavior_surface_router.py`
- `tests/test_card_behavior_router.py`
- `src/hsconfig/semantic_intent_score.py` (minimal integration blocker fix)
- `.superpowers/sdd/task-3-report.md`

RED summary:
- Ran `python -m pytest tests\test_card_behavior_router.py -q -p no:cacheprovider` after adding integration tests and before router implementation.
- Expected failures observed:
  - Mind Sear semantic value still returned `6` instead of `10`.
  - Explicit runtime value row kept value `8` but had no `semantic_score` metadata.

GREEN summary:
- Ran `python -m pytest tests\test_semantic_intent_score.py tests\test_card_behavior_router.py -q -p no:cacheprovider`.
- Result: `46 passed in 0.20s`.

Implementation summary:
- Imported `score_card_behavior_claim` into `card_behavior_surface_router.py`.
- `_attach_behavior_fields()` now scores accepted CardID behavior rows after behavior block, intent, roles, rule suffix, and condition are selected.
- Accepted rows receive `value` from the scorer and diagnostic `semantic_score` metadata with `band`, `reason`, `profile`, and `matched_signals`.
- Explicit source `runtime_value`/`value` still wins through the scorer and reports `reason == "explicit_runtime_value"`.
- Suppressed rows are not scored.

Scope note:
- `src/hsconfig/semantic_intent_score.py` required a minimal fix because its board-tempo rule matched `mech` inside `mechanic_usage`, causing unrelated generic mechanic rows to score as `8`. The fix now treats `mech` as a standalone token.

Commit:
- Created with message `feat: score accepted card behavior rows`; exact final HEAD hash is in the worker final answer.

Concerns:
- The branch started dirty because `.superpowers/sdd/progress.md` was already modified. It was not edited or staged by this task.

## Review Fix: Align Semantic Scoring Expectations

Status: done

Review context:
- Task 3 review returned NEEDS_CHANGES because broader regression tests still expected pre-scorer default values in accepted CardID behavior rows.
- No source bug was found for this review pass; the intended scorer integration now emits semantic values for accepted rows.

Files changed:
- `tests/test_no_default_only_semantic_archetype_matrix.py`
- `tests/test_prepare_cli.py`
- `tests/test_shadowpriest_depth_e2e.py`
- `.superpowers/sdd/task-3-report.md`

Expectation updates:
- SyntheticLocationDruid location runtime expectation changed from `6` to `8`, with report-layer `semantic_score.reason == "location_tempo"`.
- Resolved Discover and generic Discover accepted rows changed from `6` to `8`, with report-layer `semantic_score.reason == "draw_cycle"`.
- Darkbishop `SW_448` hero-power effect row changed from `6` to `10`, with report-layer `semantic_score.reason == "hero_power_transform"`.
- The core Darkbishop boundary remains asserted: `SW_448` is absent from concrete Mulligan keeps.

Review-fix verification:
- `python -m pytest tests\test_no_default_only_semantic_archetype_matrix.py::test_semantic_archetype_fixture_remains_load_safe_and_not_default_only[SyntheticLocationDruid] -q -p no:cacheprovider`
  - Result: `1 passed in 1.66s`.
- `python -m pytest tests\test_prepare_cli.py::test_prepare_routes_option_claim_with_identity_links tests\test_prepare_cli.py::test_prepare_partial_discover_choice_resolution_preserves_unresolved_generic_fallback -q -p no:cacheprovider`
  - Result: `2 passed in 0.61s`.
- `python -m pytest tests\test_shadowpriest_depth_e2e.py::test_shadowpriest_source_backed_strong_preserves_darkbishop_effect_not_keep -q -p no:cacheprovider`
  - Result: `1 passed in 9.29s`.
- `python -m pytest tests\test_semantic_intent_score.py tests\test_card_behavior_router.py -q -p no:cacheprovider`
  - Result: `46 passed in 0.17s`.

Review-fix concerns:
- `.superpowers/sdd/progress.md` remains pre-existing dirty state and was not edited or staged by this fix.

## Re-review Fix: Preserve Explicit Darkbishop Runtime Value

Status: done

Re-review context:
- Full-suite re-review found that `test_shadowpriest_darkbishop_effect_visible_without_mulligan_keep` uses `tests/fixtures/shadowpriest_guide_sources.json`, which explicitly supplies `runtime_value: "6"` for `SW_448`.
- Per Task 3 plan, explicit source `runtime_value`/`value` is authoritative and must win over semantic scoring.

Expectation update:
- Restored that guide-sources fixture test to expect runtime row value `6`.
- Updated its report-layer assertion to expect `semantic_score.reason == "explicit_runtime_value"`.
- Left the source-documents strong fixture test expecting semantic `10` with `hero_power_transform`, because that fixture does not provide the explicit override.

Re-review concerns:
- `.superpowers/sdd/progress.md` remains pre-existing dirty state and was not edited or staged by this fix.

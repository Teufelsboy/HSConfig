# Task 4 Fix Report

## Scope

Fixed the Task 4 review finding that CtAPaladin, Discolock, TreantDruid, and PirateDH were expected partial but still advertised as core source-backed-strong fixtures.

## Root Cause

The four rows already had `expected_semantic_status=SOURCE_BACKED_PARTIAL`, but their matrix stage and visibility metadata still used the old strong fixture contract:

- `fixture_stage=core_source_backed_fixture`
- `strongness_visibility.current_stage=core_source_backed_fixture`
- `first_strongness_gap=none`
- `operator_action=keep_as_core_control_fixture`

That kept `tests/test_strong_fixture_closure.py` running the strict strong assertions against rows whose prepare output is load-safe partial.

## Changes

- Moved CtAPaladin, Discolock, TreantDruid, and PirateDH to `source_informed_valid_fixture`.
- Added explicit partial gaps, blocking reasons, closure state, and partial-preservation operator actions for those rows.
- Kept remaining `core_source_backed_fixture` rows strict: core rows must still prepare as `SOURCE_BACKED_STRONG`.
- Added a load-safe partial regression test asserting partial rows are `VALID_PACKAGE`, `runtime_apply_allowed=true`, `runtime_apply_mode=load_safe_apply`, and not `SOURCE_BACKED_STRONG`.
- Updated closure documentation so the four reviewed decks are no longer listed as strong in active closure targets or the blocker snapshot.

## Evidence

Red before fix:

- `python -m pytest tests/test_strong_fixture_closure.py tests/test_multideck_source_backed_e2e.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_archetype_source_fixtures.py tests/test_matrix_current_truth.py tests/test_archetype_fixture_matrix.py -q`
- Result: `4 failed, 67 passed, 2 skipped`
- Failures: CtAPaladin, Discolock, TreantDruid, and PirateDH failed the core strong fixture assertion because their operator semantic statuses were partial/load-safe rather than `SOURCE_BACKED_STRONG`.

Green after fix:

- `python -m pytest tests/test_strong_fixture_closure.py tests/test_matrix_current_truth.py tests/test_archetype_fixture_matrix.py -q`
- Result: `24 passed, 11 skipped`
- `python -m pytest tests/test_strong_fixture_closure.py tests/test_multideck_source_backed_e2e.py tests/test_no_default_only_semantic_archetype_matrix.py tests/test_archetype_source_fixtures.py tests/test_matrix_current_truth.py tests/test_archetype_fixture_matrix.py -q`
- Result: `73 passed, 11 skipped`

## Concern

There are unrelated dirty files from Task 5/6 in the worktree. They were not touched for this fix and must not be staged with this commit.

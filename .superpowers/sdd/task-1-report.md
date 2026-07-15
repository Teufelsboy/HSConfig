# Task 1 Report: Strong Harvester Contract Tests

## Status

DONE_WITH_REVIEW_FIX

## Scope

- Added `tests/test_source_backed_strong_harvester_closure.py`.
- Added the minimal `strong_closure_summary` payload to the source autopilot report.
- Did not modify the existing source-search fixture because the contract tests use deterministic acquired source records and do not consume that fixture.

## Contract Coverage

- A current, full-text, deck-matched ShadowPriest mulligan guide creates keep rows for the four named cards.
- Darkbishop Benedictus remains a `hero_power_transform` evidence row and is not inferred as `mulligan_keep`.
- That complete public guide path reports `SOURCE_BACKED_STRONG`, `source_backed_strong_ready=true`, and `first_missing_source_action=none`.
- A decklist-only PirateDH source stays technically non-blocking but reports `SOURCE_BACKED_PARTIAL`, `source_backed_strong_ready=false`, and `first_missing_source_action=add_explicit_mulligan_source`.

## Implementation

Initial Task 1 added `strong_closure_summary`, but the first implementation derived `SOURCE_BACKED_STRONG` from `bool(strong_rows) and has_explicit_mulligan_source`. Review correctly identified that as a second, weaker closure engine.

The review fix now passes the existing hard gate into `_build_strong_closure_summary(...)`:

- `strong_candidate` is still computed by `_strong_candidate_blockers(...)`.
- `source_backed_strong_ready` is true only when `strong_candidate` is true, at least one strong runtime evidence row exists, and an explicit mulligan source exists.
- `strong_candidate_blockers` are copied into the nested summary so partial results explain why they did not promote.
- Top-level `first_missing_source_action` now reuses the nested summary action, avoiding disagreement between report levels.

This preserves `technical_no_block=true`: partial source closure remains visible but does not block package generation.

## Verification

Red phase:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_backed_strong_harvester_closure.py -q
```

Result before implementation: `2 failed`, both due solely to a missing `strong_closure_summary` key.

Green phase:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_backed_strong_harvester_closure.py -q
$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py tests/test_source_acquisition.py tests/test_source_claim_compiler.py -q
```

Result: `2 passed` focused tests and `34 passed` directly affected existing tests.

`git diff --check` completed with no whitespace errors.

Review-fix red phase:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_source_autopilot.py -q
```

Result before the fix: `4 failed, 13 passed`. Failures showed the nested summary promoted partial/effect-only guide rows independently from `strong_candidate`, and top-level `first_missing_source_action` disagreed with the nested summary.

Review-fix green phase:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_source_autopilot.py -q
$env:PYTHONPATH='src'; python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_source_autopilot.py tests/test_source_acquisition.py tests/test_source_claim_compiler.py -q
```

Result: `17 passed` focused closure/autopilot tests and `37 passed` requested Task-1 review-fix suite.

Additional regression coverage:

- Positive case asserts `technical_no_block`, `source_backed_strong_ready`, `semantic_status`, and `first_missing_source_action` for the full ShadowPriest fixture that has both mulligan and apply-surface closure.
- Partial cases assert the same fields and verify top-level/nested `first_missing_source_action` agreement.
- A negative ShadowPriest guide with explicit mulligan plus `SW_448` hero-power effect but no apply-surface candidate stays `SOURCE_BACKED_PARTIAL`.
- Darkbishop Benedictus / `SW_448` remains an effect row and is not inferred as a mulligan keep.

The controller-approved Task-1 scope included a preflight correction, so this report records the implementation and review fix rather than rewriting history to red-test-only.

## Concerns

None.

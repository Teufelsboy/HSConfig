# Task 1 Report: Strong Harvester Contract Tests

## Status

DONE

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

`_build_strong_closure_summary(...)` derives an evidence-quality result only from current, full-text, deck-matched guide rows that are valid runtime-contract candidates. It is deliberately independent from the pre-existing `strong_candidate` field, which also requires apply-surface evidence. The summary always exposes `technical_no_block=true`, preserving package generation as a non-gated path.

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

## Concerns

None.

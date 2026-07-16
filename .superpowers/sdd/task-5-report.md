# Task 5 Report: Make Closure Reports Actionable By Card And Surface

## Status

DONE

## Red Evidence

Added `test_partial_deck_reports_specific_missing_card_and_surface_actions` in
`tests/test_source_autopilot.py` before the production change. The required
precision run then failed because the evidence-free `DEEP_014` card received the
generic action instead of the Kingslayer-specific action:

```text
python -m pytest -p no:cacheprovider tests\test_source_autopilot.py::test_partial_deck_reports_specific_missing_card_and_surface_actions -q
1 failed
AssertionError: assert 'add_current_card_specific_runtime_source' == 'add_kingslayer_quick_pick_mulligan_source'
```

## Implementation

- Added a minimal profile-aware fallback for cards with no evidence rows.
- Preserved existing claim-kind actions when a card has partial evidence.
- Added exact Kingslayer `DEEP_014` and Boarlock `WW_092` missing-source actions.
- Added the generic profile-gap and Quick Pick Mulligan fallbacks from the task brief.
- Added the no-block matrix visibility assertion for non-strong source closure.
- Kept closure reporting diagnostic-only; `SOURCE_BACKED_STRONG` remains an apply-independent status.

## Green Evidence

The precision test passed after implementation:

```text
1 passed in 0.31s
```

The required focused suite passed:

```text
python -m pytest -p no:cacheprovider tests\test_source_autopilot.py tests\test_universal_wild_no_block_matrix.py -q
51 passed in 24.08s
```

`git diff --check` also passed.

## Changed Files

- `src/hsconfig/source_autopilot.py`
- `tests/test_source_autopilot.py`
- `tests/test_universal_wild_no_block_matrix.py`
- `.superpowers/sdd/task-5-report.md`

## Commit

Implementation and test commit:

`fix: expose precise source closure actions`

Commit SHA is recorded after the implementation commit and before this report's documentation commit.

`ea937e110e95defbba6127dfa7e131470f7addf9`

## Concerns

- The task brief's original set-membership assertion allowed the old generic action and therefore passed before implementation. The test was strengthened to assert the requested precise Kingslayer action so the mandated red phase was meaningful.
- No runtime writers, source text extraction, fixtures, docs outside this report, or apply gates were changed.

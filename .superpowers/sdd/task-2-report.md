# Task 2 Report: Warning Boundary Summary Rows

## Outcome
Implemented `warning_boundaries` on mechanic visibility summaries and carried the field through operator summary and operator guidance defaults/passthroughs.

## TDD Evidence
- Initial focused test run before code changes: `python -m pytest tests/test_mechanic_support.py tests/test_operator_summary.py tests/test_operator_guidance.py -q`
- Result: 56 passed. The suite was still on the pre-task assertions, so this confirmed the baseline rather than the new contract.
- After implementation and test updates: `python -m pytest tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py -q`
- Result: 73 passed.

## Files Changed
- `src/hsconfig/mechanic_support.py`
- `src/hsconfig/operator_summary.py`
- `src/hsconfig/operator_guidance.py`
- `tests/test_mechanic_support.py`
- `tests/test_config_readiness.py`
- `tests/test_operator_summary.py`
- `tests/test_operator_guidance.py`

## What Changed
- Added `warning_boundaries` generation to `summarize_mechanic_visibility`.
- Kept `first_warning_boundary` and `non_blocking` intact.
- Made `first_warning_boundary` deterministic by selecting the warning-only row with the lowest `card_id`, which preserves the brief’s expected `dredge` result when `board_position` is also present.
- Preserved and sanitized `warning_boundaries` in operator summary and operator guidance fallback structures.
- Updated visible tests to cover the new field on the direct summary, operator summary passthrough, operator guidance passthrough, and config readiness output.

## Concerns
- None beyond the existing CRLF line-ending warnings reported by Git on modified files. The test suite passed, and no adjacent behavior outside Task 2 surfaces was changed.

## Fix Follow-up
- Reviewer finding: `first_warning_boundary` in `src/hsconfig/mechanic_support.py` had been changed to prefer the lexicographically smallest `card_id`, which broke the original first-encounter semantics.
- Exact fix: removed the `card_id` tie-break from `summarize_mechanic_visibility`, so `first_warning_boundary` is now set on the first warning-only row encountered in row/support iteration order. Kept `warning_boundaries` as the sorted unique mechanic list.
- Test adjustment: `tests/test_mechanic_support.py` now asserts the first warning boundary follows the input row order instead of the `card_id` sort path.
- Verification command: `$env:PYTHONPATH='src'; python -m pytest tests/test_mechanic_support.py tests/test_config_readiness.py tests/test_operator_summary.py tests/test_operator_guidance.py -q`
- Result: `73 passed in 0.27s`

# Task 9 low-confidence verification fix

## Root cause

`src/hsconfig/config_readiness.py::_lane_and_missing_link()` evaluated
`suppressed_mulligan_cards` before the low-confidence and uncovered-card checks.
That let `claim_not_runtime_lowerable` suppressed mulligan rules reclassify cards
as `report_only_supported` with `needs_mulligan_claim`, even when the card was
still `generic_low_confidence` or explicitly uncovered. The result was that
Task 9 verification undercounted `generic_low_confidence` rows in prepare output.

## Changes

1. Added a focused regression test in
   `tests/test_config_readiness.py::test_suppressed_mulligan_claim_does_not_hide_generic_low_confidence_gap`.
   It proves a suppressed mulligan claim does not override a card that is both
   `generic_low_confidence` and uncovered.
2. Adjusted `_lane_and_missing_link()` so suppressed mulligan credit only applies
   after low-confidence classification and only for guide/source-backed coverage
   (`is_guide_backed`).

## Tests

- `python -m pytest tests/test_config_readiness.py::test_suppressed_mulligan_claim_does_not_hide_generic_low_confidence_gap -q`
  - red: failed with `report_only_supported != generic_low_confidence`
  - green: passed after the fix
- `python -m pytest tests/test_prepare_cli.py::test_prepare_low_confidence_source_documents_do_not_lower_runtime_rows tests/test_prepare_cli.py::test_prepare_low_confidence_claims_json_does_not_lower_runtime_rows -q`
- `python -m pytest tests/test_config_readiness.py tests/test_prepare_cli.py -q`

## Concerns

- Git reports existing LF-to-CRLF normalization warnings for the touched files.
  No functional changes were made beyond the scoped readiness fix and test.

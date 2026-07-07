# Task 2 Report: Seven-Deck Closure Fixture Test Harness

## Scope

- Modified: `tests/helpers/fixture_prepare.py`
- Added: `tests/test_fixture_source_depth_closure.py`
- No fixture, matrix, production module, doc, or runtime output edits

## TDD Record

### RED

Command:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py -q
```

Observed result:

- Exit code: `1`
- Failures: `7`
- Failure mode: every parametrized deck failed on `KeyError: 'source_claim_gap_report'`
- Representative location: `tests/test_fixture_source_depth_closure.py:29`

Interpretation:

- The new harness test was exercising the intended interface.
- `prepare_fixture_deck()` already produced `reports/source_claim_gap_report.json` and `reports/strong_promotion_report.json` on disk, but its returned dictionary exposed only `source_gap`, not the planned `source_claim_gap_report` key, and did not expose `strong_promotion_report`.

### GREEN

Minimal helper change applied:

- Added a small `read_json()` helper for existing report loads.
- Preserved existing return keys.
- Added:
  - `source_claim_gap_report` as an alias of the existing `source_gap`
  - `strong_promotion_report` loaded from `reports/strong_promotion_report.json`

Command:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py -q
```

Observed result:

- Exit code: `0`
- Result: `7 passed in 6.54s`

## Requirement Coverage

- Seven source-informed decks are selected by name in the new harness test.
- Each row must compile through `prepare_fixture_deck()`.
- The harness asserts:
  - `exit_code == 0`
  - `technical_status == VALID_PACKAGE`
  - normal-path optional files `Presume.json` and `Concede.json` are absent
  - if promotion is ready, semantic status and next action are the strong-path values and no closure gap remains
  - otherwise, the test requires an exact actionable first missing chain with an allowed missing-link type and a next action

## Notes

- Existing helper key drift from the plan was real: the helper exposed `source_gap` instead of `source_claim_gap_report`.
- I adapted minimally by preserving `source_gap` and adding the planned keys, which keeps existing helper consumers stable.

## Commit

Planned commit message:

```text
test: add source-informed fixture closure harness
```

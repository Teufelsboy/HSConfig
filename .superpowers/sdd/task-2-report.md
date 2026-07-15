# Task 2 Report

- Status: DONE
- Scope: Task-2 files only plus this report.
- Files changed:
  - `src/hsconfig/source_acquisition.py`
  - `src/hsconfig/source_claim_compiler.py`
  - `tests/test_source_acquisition_strong_closure.py`
  - `tests/test_source_claim_compiler.py`
  - `.superpowers/sdd/task-2-report.md`
- Requirements covered:
  - Current full-text deck/mulligan guides expose `strong_promotion_eligible=True` and `first_missing_source_action=none`.
  - Decklist-only, snippet-only, stale, and static/card-text evidence remains non-strong and diagnostic/non-promoting.
  - Acquisition now emits stable narrow metadata aliases: `source_category`, `source_document_kind`, and `source_strength`.
  - Claim compiler preserves `source_strength` and emits `claim_family` for lowerable and non-promoting claims.
  - Darkbishop-style start-of-game effect text remains `hero_power_transform` / `card_effect` and does not create a `mulligan_keep`.
  - No runtime/apply authority was added; this task only marks source/claim evidence quality.
- Red evidence:
  - Command: `$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition_strong_closure.py tests/test_source_claim_compiler.py -q`
  - Result: `6 failed, 11 passed`
  - Expected failures: missing `source_category`, `source_strength`, and `claim_family` fields.
- Green evidence:
  - Command: `$env:PYTHONPATH='src'; python -m pytest tests/test_source_acquisition_strong_closure.py tests/test_source_claim_compiler.py -q`
  - Result: `17 passed in 0.20s`
- Self-review:
  - Diff stayed inside the requested write scope.
  - Existing no-block behavior is unchanged: weak sources remain visible diagnostics instead of package-generation blockers.
  - Git reported only line-ending normalization warnings during diff/stat commands.

## Review Fix

- Issue: non-promoting guide-shaped records such as `source_type=default_runtime` could lose their source-policy metadata in the compiler and later be reclassified as strong by Autopilot.
- Fix:
  - `source_type`, `provenance`, `promotion_eligible`, `strong_promotion_eligible`, `promotion_blockers`, and `first_missing_source_action` now survive acquisition -> compiler.
  - If the source record is non-promoting, compiled claims are also marked `promotion_eligible=false`.
  - Added `test_compile_default_runtime_guide_claims_are_non_promoting`.
  - Updated the stale online-source thin-deck expectation to the newer precise `add_explicit_mulligan_source` action.
- Green evidence:
  - Command: `$env:PYTHONPATH='src'; python -m pytest tests/test_source_claim_compiler.py::test_compile_default_runtime_guide_claims_are_non_promoting -q`
  - Result: `1 passed in 0.14s`
  - Command: `$env:PYTHONPATH='src'; python -m pytest tests/test_configure_online_source.py -q`
  - Result: `4 passed in 1.17s`
  - Command: `$env:PYTHONPATH='src'; python -m pytest tests/test_source_backed_strong_harvester_closure.py tests/test_source_acquisition_strong_closure.py tests/test_source_claim_compiler.py tests/test_source_autopilot.py tests/test_strong_closure_ledger.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py tests/test_configure_online_source.py -q`
  - Result: `69 passed in 1.69s`

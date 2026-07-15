Status: DONE

Files changed
- `src/hsconfig/operator_summary.py`
- `tests/test_operator_summary.py`
- `tests/test_source_to_runtime_explainability.py`
- `.superpowers/sdd/task-4-report.md`

Requirements implemented
- Kept `VALID_PACKAGE` and `runtime_apply_allowed=True` intact for partial/non-strong source packages.
- Added source quality lane-count semantic blockers for non-strong evidence lanes:
  - `policy_fallback` -> `policy_claim_not_strong_evidence`
  - `default_runtime` -> `default_runtime_not_strong_evidence`
  - `snippet_only` -> `snippet_only_source_not_strong_evidence`
- Wired those blockers into the existing semantic-status path so they block only `SOURCE_BACKED_STRONG`, not technical validity or load-safe apply.
- Added an operator-summary regression proving `default_runtime` and `snippet_only` lane counts keep a package valid and apply-allowed while preventing strong promotion.
- Added the brief's explicit explainability regression for policy-backed runtime rows exposing:
  - `source_lane=policy_fallback`
  - `runtime_lowering_status=policy_backed_runtime`
  - `first_missing_source_action=add_explicit_mulligan_source`

Tests run, exact command and result
- `$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py -q`
  - Initial TDD result: `1 failed, 95 passed in 0.77s`
  - Expected failure: `test_operator_summary_source_quality_lanes_block_strong_without_blocking_apply` did not find `default_runtime_not_strong_evidence`.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py -q`
  - Final result: `107 passed in 0.57s`

TDD evidence if applicable
- Added `test_operator_summary_source_quality_lanes_block_strong_without_blocking_apply` before production changes.
- Confirmed red state: the new test failed because the operator summary had no source-quality lane blockers for `default_runtime` and `snippet_only`.
- Implemented the minimal production hook in `operator_summary.py`.
- Re-ran the targeted task verification set and confirmed green.

Self-review notes
- Change is limited to semantic strongness evidence only.
- No new apply/load gate was added.
- `source_to_runtime_explainability.py` already exposed the required fields and mapping, so no production edit was needed there.
- Existing policy/default-only surface blockers remain unchanged.
- The report file had stale content from a different Task 4 slice and was replaced with this task's required report.

Concerns
- An unrelated untracked file exists and was not touched: `docs/superpowers/plans/2026-07-15-hsconfig-source-acquisition-strong-closure.md`.
- Git reports line-ending normalization warnings for touched LF files; no content issue was observed in the diff.

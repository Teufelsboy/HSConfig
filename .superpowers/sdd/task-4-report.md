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

Review fix update - 2026-07-15 18:58:17 +02:00

Files changed
- `src/hsconfig/operator_summary.py`
- `tests/test_operator_summary.py`
- `.superpowers/sdd/task-4-report.md`

Fix details
- Expanded source quality lane-count handling to current producer lane names.
- `policy_fallback` and `policy_backed` now emit `policy_claim_not_strong_evidence`.
- `decklist_only` now emits `decklist_only_not_strong_evidence`.
- Other non-strong producer lanes now block only strong promotion: `default_runtime`, `snippet_only`, `archetype_inferred`, `explicit_low_confidence`, `generic_low_confidence`, and `contract_gap`.
- Added a positive strong lane requirement only when `source_quality_lane_counts` is present.
- Positive strong lanes accepted for strong promotion are `deck_matched_public_guide`, `guide_backed`, `source_backed_static_semantics`, `official_static_semantics`, and `static_semantics_backfilled`.
- Missing positive strong lane now emits `missing_positive_strong_source_lane`.
- Technical status and runtime apply permission remain unchanged; blockers are semantic strongness evidence only.

Regression coverage added
- `policy_backed` plus `guide_backed` stays `VALID_PACKAGE` and apply-allowed, but not `SOURCE_BACKED_STRONG`.
- `decklist_only` plus `guide_backed` stays `VALID_PACKAGE` and apply-allowed, but not `SOURCE_BACKED_STRONG`.
- Present lane summaries with `generic_low_confidence` only or `{}` do not promote just from `source_backed` depth and positive claim count.
- `guide_backed` only still permits `SOURCE_BACKED_STRONG`.

Tests run, exact command and result
- `$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py -q`
  - TDD red after fixture correction: `4 failed, 83 passed in 0.81s`.
  - Expected failures: `policy_backed`, `decklist_only`, `generic_low_confidence`, and empty lane summaries still promoted to `SOURCE_BACKED_STRONG`.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py -q`
  - Green after fix: `87 passed in 0.51s`.
- `$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py -q`
  - Final result: `112 passed in 0.39s`.

Concerns
- No new concerns.

Review fix update - policy_fallback coverage

Files changed
- `tests/test_operator_summary.py`
- `.superpowers/sdd/task-4-report.md`

Fix details
- Added direct `source_quality_lane_counts={"policy_fallback": 1, "guide_backed": 1}` coverage for the operator-summary lane-count path.
- The regression asserts `VALID_PACKAGE`, `runtime_apply_allowed=true`, no `SOURCE_BACKED_STRONG`, and `policy_claim_not_strong_evidence`.

Tests run, exact command and result
- `$env:PYTHONPATH='src'; python -m pytest tests/test_operator_summary.py tests/test_source_to_runtime_explainability.py tests/test_strong_promotion_report.py -q`
  - Final result after policy_fallback coverage: `113 passed in 0.61s`.

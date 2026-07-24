# Current Task 2: Embed Source Readiness Preview

Status: review hygiene complete

Current-task index:
- Current implementation report: `## Task 2: Embed Source Readiness Preview`
- Review hygiene fix: `## Review Fix: Source Readiness Preview Value Propagation`
- Important review fix: `## Review Fix: Authoritative None Source Action`
- Historical Task-2 report entries are preserved below for audit history.

# Task 2 Report: Semantic Intent Scorer

Status: complete

Files changed:
- `src/hsconfig/semantic_intent_score.py`
- `.superpowers/sdd/task-2-report.md`

Verification:
- RED before implementation: `python -m pytest tests\test_semantic_intent_score.py -q -p no:cacheprovider`
  - Result: failed during collection with `ModuleNotFoundError: No module named 'hsconfig.semantic_intent_score'`.
- Post-implementation tests: `python -m pytest tests\test_semantic_intent_score.py -q -p no:cacheprovider`
  - Result: `5 passed in 0.07s`.
- Compile check: `python -m py_compile src\hsconfig\semantic_intent_score.py`
  - Result: exit 0.
- Diff whitespace check: `git diff --check -- src/hsconfig/semantic_intent_score.py tests/test_semantic_intent_score.py .superpowers/sdd/task-2-report.md`
  - Result: exit 0; Git emitted only an LF-to-CRLF warning for this Markdown file.

Commit hash:
- The exact commit hash is reported in the final worker response after commit creation.

Concerns:
- `.superpowers/sdd/progress.md` was already modified outside this task and was left untouched.
- The task requested a report file containing the final commit hash, but a commit cannot contain its own hash as stable content. The final response carries the exact hash.

## Review Fix: Explicit Value Fallback And Default Bounds

Status: complete

Files changed:
- `src/hsconfig/semantic_intent_score.py`
- `tests/test_semantic_intent_score.py`
- `.superpowers/sdd/task-2-report.md`

Fixes:
- Blank `runtime_value` now falls through to a non-blank explicit `value` and still reports `reason="explicit_runtime_value"`.
- Non-explicit semantic default fallback values are now clamped to the supported helper range `4` through `12`.
- Explicit source values remain authoritative and are not clamped by the fallback helper.

Verification:
- RED after adding review regression tests: `python -m pytest tests\test_semantic_intent_score.py -q -p no:cacheprovider`
  - Result: `2 failed, 5 passed`; failures covered blank `runtime_value` fallback and unclamped low default.
- Post-fix scorer tests: `python -m pytest tests\test_semantic_intent_score.py -q -p no:cacheprovider`
  - Result: `7 passed in 0.09s`.
- Compile check: `python -m py_compile src\hsconfig\semantic_intent_score.py`
  - Result: exit 0.

## Task 2: Source Freshness Provenance Normalizer

Status: complete

Files changed:
- `src/hsconfig/source_evidence_policy.py`
- `src/hsconfig/source_autopilot.py`
- `tests/test_source_autopilot.py`
- `.superpowers/sdd/task-2-report.md`

TDD evidence:
- RED after adding the required provenance tests:
  `python -m pytest tests/test_source_autopilot.py::test_rank_public_sources_exposes_current_or_evergreen_provenance tests/test_source_autopilot.py::test_source_evidence_rows_preserve_provenance_projection -q`
  - Result: `2 failed`; both failures were expected `KeyError: 'freshness_status'` from the missing ranked/evidence-row projections.
- GREEN after wiring `normalize_source_provenance` through policy and autopilot:
  `python -m pytest tests/test_source_autopilot.py::test_rank_public_sources_exposes_current_or_evergreen_provenance tests/test_source_autopilot.py::test_source_evidence_rows_preserve_provenance_projection -q`
  - Result: `2 passed in 0.32s`.
- Focused regression suite:
  `python -m pytest tests/test_source_autopilot.py -q`
  - Result: `35 passed in 7.57s`.
- Compile and whitespace checks:
  `python -m py_compile src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py` and `git diff --check -- src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py tests/test_source_autopilot.py .superpowers/sdd/task-2-report.md`
  - Result: exit 0. Git emitted only existing line-ending conversion warnings.

Self-review:
- `source_freshness_lane`, source rank lanes, promotion blockers, and source lane semantics remain owned by existing policy code and are unchanged.
- Provenance is an additive diagnostic projection; `source_status_apply_blocking` is explicitly `False` and is not used as an apply gate.
- Both ranking and evidence-row construction receive the same deck identity, preserving deck-identity provenance in derived rows.
- No runtime, gameplay, Mulligan, default-only surface, dependency, or research changes were made.

Commit info:
- Commit message: `feat: expose source provenance in autopilot`.
- The resulting commit hash is supplied in the task response because a commit cannot stably record its own final hash.

## Task 2: Embed Source Readiness Preview

Status: complete

Files changed:
- `src/hsconfig/source_autopilot.py`
- `src/hsconfig/commands/configure.py`
- `tests/test_source_autopilot.py`
- `tests/test_configure_online_source.py`
- `.superpowers/sdd/task-2-report.md`

TDD evidence:
- RED after adding the required preview assertions:
  `pytest tests/test_source_autopilot.py tests/test_configure_online_source.py -q`
  - Result: `3 failed, 46 passed in 11.13s`; failures were expected `KeyError: 'source_readiness_preview'` in the autopilot report and configure summary paths.
- GREEN after embedding `build_source_readiness_preview` in autopilot and configure:
  `pytest tests/test_source_readiness_preview.py tests/test_source_autopilot.py tests/test_configure_online_source.py -q`
  - Result: `55 passed in 11.09s`.

Implementation notes:
- `source_autopilot_report["source_readiness_preview"]` is built from the in-memory autopilot report only.
- `configure_summary["source_readiness_preview"]` is built from the existing `source_candidate_plan`, optional `source_autopilot_report.json`, and `operator_summary`.
- The preview remains diagnostic-only and keeps `runtime_apply_authority` fixed at `reports/operator_summary.json`.
- No runtime writes, apply gates, second apply authority, HSTuner paths, log parsing, replay parsing, HDT parsing, or gameplay evaluation were added.

Open risks:
- No broader full-repo suite was run; verification was limited to the Task-2 targeted suites from the brief plus the existing preview helper tests.
- `.superpowers/sdd/progress.md` was already modified outside this task and was left untouched.

## Review Fix: Source Readiness Preview Value Propagation

Status: complete

Files changed:
- `tests/test_configure_online_source.py`
- `.superpowers/sdd/task-2-report.md`

Fix note:
- Added configure-summary assertions that `source_readiness_preview["first_missing_source_action"]` is propagated from `reports/operator_summary.json` and that `recommended_next_source_action` mirrors the first missing source action.
- Added a current-task header/index at the top of this report so the active Task 2 section is visible before older historical report entries.
- The preferred operator field existed in the ShadowPriest fixture, so no fallback assertion was needed.

Verification:
- `pytest tests/test_source_readiness_preview.py tests/test_source_autopilot.py tests/test_configure_online_source.py -q`
  - Result: `55 passed in 9.81s` on the latest rerun after all code edits.

## Review Fix: Authoritative None Source Action

Status: complete

Files changed:
- `src/hsconfig/source_readiness_preview.py`
- `tests/test_source_readiness_preview.py`
- `.superpowers/sdd/task-2-report.md`

Fix note:
- Added a regression test for `operator_summary["first_missing_source_action"] == "none"` with lower-precedence Autopilot and Candidate Plan non-none actions.
- `_first_action` now distinguishes a missing `first_missing_source_action` key from an explicit `"none"` value. Explicit `"none"` from the operator/autopilot/strong closure path prevents lower-precedence source actions from rewriting the preview action.
- Default-only runtime surfaces remain visible as the default-only source action and do not become hidden source-backed-strong readiness.

Verification:
- RED before implementation:
  `pytest tests/test_source_readiness_preview.py::test_preview_keeps_operator_none_authoritative_over_lower_source_actions -q`
  - Result: `1 failed`; expected `"none"`, actual `add_current_card_specific_runtime_source`.
- GREEN after fix:
  `pytest tests/test_source_readiness_preview.py::test_preview_keeps_operator_none_authoritative_over_lower_source_actions -q`
  - Result: `1 passed in 0.10s`.
- Targeted review suite:
  `pytest tests/test_source_readiness_preview.py tests/test_source_autopilot.py tests/test_configure_online_source.py -q`
  - Result: `56 passed in 11.43s`.

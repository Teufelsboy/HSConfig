STATUS: DONE

Files changed
- src/hsconfig/source_evidence_policy.py
- tests/test_source_evidence_policy.py
- .superpowers/sdd/task-1-report.md (report only, not committed per commit scope)

Commit(s)
- 76ca1fe feat: classify evergreen Wild source evidence

RED test command and failure summary
- Command: python -m pytest tests/test_source_evidence_policy.py -q
- Result: exit 1, 3 failed and 7 passed.
- Expected failures: missing source_freshness_lane raised KeyError in the two freshness tests; stats aliases still returned source_unclassified instead of statistical_enrichment.

GREEN test command and pass summary
- Command: python -m pytest tests/test_source_evidence_policy.py -q
- Result: exit 0, 10 passed in 0.18s.

Self-review notes
- Implemented the requested source_freshness_lane classification, evergreen Wild guide rank lane, stats family aliases, promotion blockers, missing-source action mapping, and helper functions.
- Reviewed the assigned-file diff and ran git diff --check for the assigned files; no whitespace errors were reported, only Git LF/CRLF working-copy warnings.
- Staged and committed only src/hsconfig/source_evidence_policy.py and tests/test_source_evidence_policy.py.
- Existing unrelated workspace changes in .superpowers/sdd/progress.md and docs/superpowers/plans/2026-07-16-hsconfig-source-closure-autopilot-v2.md were left untouched.

Review fix
- Reviewer finding: duplicate matched_card_ids could satisfy the evergreen Wild minimum match threshold.
- Root cause: _matched_card_count counted list entries rather than unique non-empty card IDs.
- RED command: python -m pytest tests/test_source_evidence_policy.py::test_evergreen_wild_archetype_requires_two_unique_matched_cards -q
- RED result: exit 1; expected stale_or_not_current but got evergreen_wild_archetype.
- Fix: count unique non-empty matched_card_ids.
- GREEN command: python -m pytest tests/test_source_evidence_policy.py -q
- GREEN result: exit 0; 11 passed in 0.14s.

## Task 1: Semantic Intent Scorer Unit Tests

### RED command and output evidence

- Command: `python -m pytest tests\test_semantic_intent_score.py -q -p no:cacheprovider`
- Result: exit 1 during test collection.
- Expected failure: `ModuleNotFoundError: No module named 'hsconfig.semantic_intent_score'`
- Observed traceback location: `tests\test_semantic_intent_score.py:1`, importing `SemanticIntentScore` and `score_card_behavior_claim`.
- The failure is the intended RED state because the production module does not yet exist and no production code was added in Task 1.

### Files changed

- Created `tests/test_semantic_intent_score.py` with five focused tests covering explicit runtime authority, conditional minion-death burn, hero-power transformation, location tempo, and semantic default fallback.
- Appended this Task 1 report to `.superpowers/sdd/task-1-report.md`.
- No other files were changed by this task. The pre-existing `.superpowers/sdd/progress.md` modification was left untouched.

### Self-review

- Confirmed `src/hsconfig/semantic_intent_score.py` is absent, so the RED failure is attributable to the missing requested production interface rather than an accidental import path mismatch.
- `python -m py_compile tests\test_semantic_intent_score.py` completed with exit 0.
- `git diff --check -- tests/test_semantic_intent_score.py` completed with exit 0; the new file contains no whitespace errors.
- Reviewed the test assertions against the Task 1 brief and kept the implementation scope test-only.
- No HSTuner, runtime, replay, log, or web-research workflows were used.

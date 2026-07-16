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

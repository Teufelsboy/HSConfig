Status: DONE

Files changed
- `src/hsconfig/source_autopilot.py`
- `tests/test_source_autopilot.py`
- `.superpowers/sdd/task-3-report.md`

Requirements implemented
- Added the focused source-autopilot closure-ledger regression test from the Task 3 brief.
- Added `strong_candidate_blockers` to `source_autopilot_report`.
- Added `first_missing_source_action_by_card` to `source_autopilot_report`.
- Added `non_promoting_claim_count` to `source_autopilot_report`.
- Kept the change diagnostic-only: no apply gate, load gate, runtime-write behavior, or source-document mutation was added.
- Preserved existing `strong_candidate` behavior by deriving it from the same blocker prerequisites.

Tests run, exact command and result
- `$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py::test_source_autopilot_reports_strong_blockers_per_card -q`
  - Red result before implementation: `1 failed in 0.35s`
  - Expected failure: `KeyError: 'strong_candidate_blockers'`
- `$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py::test_source_autopilot_reports_strong_blockers_per_card -q`
  - Green result after implementation: `1 passed in 0.13s`
- `$env:PYTHONPATH='src'; python -m pytest tests/test_source_autopilot.py -q`
  - Result: `13 passed in 0.18s`

TDD evidence if applicable
- Test was added first.
- Focused test failed before implementation because the new report field was missing.
- Implementation was added after the failing test was observed.
- Focused test and full source-autopilot test file passed after implementation.

Self-review notes
- `strong_candidate_blockers` is computed from the existing strong-candidate prerequisites:
  - card-specific lowerable strong guide rows
  - apply-surface strong guide rows
  - unresolved draft mentions
  - source-document verification status
  - source-document verification warnings
- Per-card closure action only marks cards as `none` when a current full-text deck-matched public guide row supplies a runtime-contract candidate for that card.
- `non_promoting_claim_count` counts explicit `promotion_eligible is False` rows and legacy/raw decklist or static `card_role` rows that are non-promoting by the completed Task 1-2 contract.
- Existing weak-source behavior remains non-blocking and visible.

Concerns
- The required fixture `source_search_decklist_only.json` still contains a raw `card_role` claim without the newer `promotion_eligible=False` marker. The report counter handles that as a diagnostic fallback without mutating evidence rows.
- Git status shows an unrelated untracked plan file outside this task's write scope: `docs/superpowers/plans/2026-07-15-hsconfig-source-acquisition-strong-closure.md`. It was left untouched.

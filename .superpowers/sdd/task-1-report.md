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

## Task 1: Pure Source Provenance Normalizer

### Scope

- Created `src/hsconfig/source_provenance.py` with the two brief-defined pure interfaces:
  `normalize_source_provenance` and `research_payload_provenance`.
- Created `tests/test_source_provenance.py` with the four brief-defined unit tests.
- No downstream consumers, runtime packages, Mulligan logic, apply authority, or source policy modules were changed.
- No HSTuner, HearthRanger logs, game logs, or online deck research were used.

### TDD evidence

- RED command: `python -m pytest tests/test_source_provenance.py -q`
- RED result: exit 1 during collection with `ModuleNotFoundError: No module named 'hsconfig.source_provenance'`.
- GREEN command: `python -m pytest tests/test_source_provenance.py -q`
- GREEN result: exit 0, `4 passed in 0.10s`.

### Implemented behavior

- Normalizes source family and visibility, including guide, decklist-only, and static-semantic families.
- Reports deck identity match and the match basis from deck name and/or card overlap.
- Classifies current, evergreen Wild, stale, not-strategy-guide, and unknown freshness states.
- Accepts nested research freshness markers and returns non-blocking source diagnostics.
- Keeps `source_status_apply_blocking` hard-coded to `False`; this helper is diagnostic provenance only.

### Verification and concerns

- The focused Task-1 test suite passed.
- The implementation is pure and has no new dependencies or runtime side effects.
- The brief-defined tests do not exhaustively cover every fallback branch; later consumer tasks should add contract-level coverage when integrating this helper.
- Final commit scope contains only `src/hsconfig/source_provenance.py`, `tests/test_source_provenance.py`, and this required Task-1 report.

## Task 1 Review Fix

### Finding and regression test

- Review finding: `_deck_identity_match` ignored `deck_identity["cards"]`, so unrelated non-empty `matched_card_ids` could falsely establish card overlap.
- Added `test_unrelated_matched_cards_do_not_establish_deck_identity_match` to prove that unrelated IDs do not match a known canonical deck.
- RED command: `python -m pytest tests/test_source_provenance.py::test_unrelated_matched_cards_do_not_establish_deck_identity_match -q`
- RED result: exit 1; the pre-fix implementation returned `deck_identity_match=True` instead of `False`.

### Fix and verification

- Passed `deck_identity` through to `_deck_identity_match`.
- Added canonical CardID extraction from `deck_identity["cards"]`; when canonical IDs exist, matched IDs count only when their sets intersect.
- Preserved deck-name-only matching and `source_status_apply_blocking=False`.
- Removed the unused `CURRENT_OR_EVERGREEN_RANK_LANES` constant.
- GREEN command: `python -m pytest tests/test_source_provenance.py -q`
- GREEN result: exit 0, `5 passed in 0.10s`.
- No downstream consumers, runtime apply/output, or dependencies were changed.

## Task 1 Review Fix 2

### Finding and regression test

- Review finding: Evergreen Wild classification still counted arbitrary `record["deck_match"]["matched_card_ids"]` without validating them against the canonical deck.
- Added `test_unrelated_wild_cards_do_not_establish_evergreen_provenance` with unrelated Wild IDs and a known deck identity.
- RED command: `python -m pytest tests/test_source_provenance.py::test_unrelated_wild_cards_do_not_establish_evergreen_provenance -q`
- RED result: exit 1; the pre-fix implementation returned `freshness_status="evergreen"` instead of `"stale"`.

### Fix and verification

- Threaded `deck_identity` through `_freshness_status` and `_is_evergreen_wild_source`.
- Extracted shared validated matched-card-ID logic; canonical overlap is required whenever canonical IDs are known, while absent/empty canonical identities retain the prior fallback.
- Preserved `current_or_evergreen=False` for the unrelated source and `source_status_apply_blocking=False`.
- GREEN command: `python -m pytest tests/test_source_provenance.py -q`
- GREEN result: exit 0, `6 passed in 0.10s`.
- No downstream consumers, runtime apply/output, or dependencies were changed.

## Task 1: Source Readiness Preview Helper

### Geaenderte Dateien

- `src/hsconfig/source_readiness_preview.py`
- `tests/test_source_readiness_preview.py`
- `.superpowers/sdd/task-1-report.md` (Report only)

### RED-Ausgabe kurz

- Command: `pytest tests/test_source_readiness_preview.py -q`
- Result: exit 1 during collection.
- Expected failure: `ModuleNotFoundError: No module named 'hsconfig.source_readiness_preview'`.

### GREEN-Ausgabe kurz

- Command: `pytest tests/test_source_readiness_preview.py -q`
- Result: exit 0, `4 passed in 0.11s`.

### Offene Risiken

- Nur die fokussierte Task-1-Testdatei wurde ausgefuehrt; keine volle Suite.
- Die bereits vorher vorhandene Aenderung an `.superpowers/sdd/progress.md` wurde nicht beruehrt.
- Kein Commit erstellt; Controller uebernimmt Commit/Review.

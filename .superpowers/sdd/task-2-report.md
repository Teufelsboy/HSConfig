# Task 2 Report: Source Autopilot Evergreen Wild Lane

## Commit

- `465c659e0e1648b8d0f01d5792354252b22a5bee`
- Message: `feat: support evergreen Wild guide autopilot lanes`

## RED Test Evidence

Command:

```powershell
python -m pytest tests/test_source_autopilot.py::test_rank_public_sources_accepts_evergreen_wild_archetype_as_strong_lane tests/test_source_autopilot.py::test_source_autopilot_evergreen_wild_guide_can_close_strong_summary tests/test_source_autopilot.py::test_source_autopilot_old_non_wild_guide_requests_current_or_evergreen_source -q
```

Result before implementation:

- `3 failed`
- Evergreen rank rows did not preserve `source_freshness_lane`.
- Evergreen Wild full-text guide still ranked as `guide_card_overlap`.
- Old non-Wild guide did not expose the required source-refresh action.

## GREEN Test Evidence

Targeted Task 2 tests:

```powershell
python -m pytest tests/test_source_autopilot.py::test_rank_public_sources_accepts_evergreen_wild_archetype_as_strong_lane tests/test_source_autopilot.py::test_source_autopilot_evergreen_wild_guide_can_close_strong_summary tests/test_source_autopilot.py::test_source_autopilot_old_non_wild_guide_requests_current_or_evergreen_source -q
```

Result:

- `3 passed in 0.15s`

Autopilot regression file:

```powershell
python -m pytest tests/test_source_autopilot.py -q
```

Result:

- `27 passed in 0.14s`

Required Task 2 verification:

```powershell
python -m pytest tests/test_source_autopilot.py tests/test_source_evidence_policy.py -q
```

Result:

- `38 passed in 0.25s`

## Files Changed

- `src/hsconfig/source_autopilot.py`
- `tests/test_source_autopilot.py`

## Notes

- `rank_public_sources(...)` now preserves policy-derived `source_freshness_lane`.
- Evergreen Wild full-text deck/archetype-matched guide rows can rank as `guide_evergreen_wild_archetype`.
- `_is_strong_guide_lane(...)` accepts both `guide_current_deck_match` and `guide_evergreen_wild_archetype`, while still requiring full text, deck-matched public guide lane, and no policy blockers.
- Stale non-evergreen full-text guide rows remain `SOURCE_BACKED_PARTIAL` and report `add_current_or_evergreen_wild_public_guide`.
- Source preflight remains diagnostic and non-blocking.

## Residual Risks

- Only the required Task 2 targeted suite was run, not the full repository test suite.
- The report file is intentionally uncommitted per task instruction.

## Review Fix

- Reviewer finding: stale non-evergreen full-text guide rows without structured claims lost the source-policy action because only extracted evidence rows were scanned.
- Root cause: ranked source rows carried `source_not_current_or_evergreen_wild`, but empty `source_evidence_rows` caused the report to fall back to the closure-profile action.
- RED command: `python -m pytest tests/test_source_autopilot.py::test_source_autopilot_stale_guide_without_claims_requests_current_or_evergreen_source -q`
- RED result: exit 1; expected `add_current_or_evergreen_wild_public_guide`, got `add_current_card_specific_runtime_source`.
- Fix: pass ranked source rows into `_build_strong_closure_summary(...)` and scan ranked source policy blockers before profile-gap fallbacks.
- GREEN command: `python -m pytest tests/test_source_autopilot.py tests/test_source_evidence_policy.py -q`
- GREEN result: exit 0; 39 passed in 0.22s.

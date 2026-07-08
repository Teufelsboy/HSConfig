# HSConfig Next Recommendation, 2026-07-08

This research-deep package turns the post-closure skill audit into a concrete
next-step recommendation.

## Recommendation

Make Boarlock the next implementation target.

Scope it as full closure of the existing Boarlock matrix row, not as a
Fracking-only patch and not as a matrix-broadening exercise. Boarlock has the
highest strategic value because it is the current `Combo.json` representative
and still exposes the deepest blocker stack: Fracking mulligan depth, runtime
surface, uncovered-card, generic-low-confidence, and unsupported-condition
signals.

## Follow-Up Order

1. Close Boarlock first.
2. Close Kingslayer second.
3. Do only small maintainability guardrails while closure work is active.
4. Keep the normal runtime surface unchanged.

## Not Recommended Now

- Do not add more representative decks before Boarlock and Kingslayer have a
  clean closure or an explicit preserved stop condition.
- Do not broaden the normal output beyond `GlobalValues.json`, `Mulligan.json`,
  CardID JSON, and exact justified `Combo.json`.
- Do not start a broad CLI or docs refactor before the remaining source-depth
  closure targets are resolved.

## Implementation Shape If Approved

The next plan should be a Boarlock closure wave:

- prove or reject the exact deck-specific Fracking mulligan claim;
- run fresh Boarlock `prepare` evidence;
- clear or preserve each remaining Boarlock blocker explicitly;
- keep `operator_summary.json` as the single gate;
- prove no runtime-surface widening occurred;
- keep Kingslayer unchanged except as a regression control;
- update the matrix only after the fresh evidence determines the correct
  Boarlock closure state.

## Validation

All recommendation JSON files passed the local research schema validator with
100 percent field coverage. Focused local tests for matrix, source-depth,
combo, and CLI surfaces passed during the research run.

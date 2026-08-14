# Pre-run Contract

[Back to the operator guide](../operator/README.md)

HSConfig accepts a deck name and exact Hearthstone deck code and produces one
deck-scoped HearthRanger VisionAI `CustomConfig` package before games begin.

## Inputs

- The decoded canonical deck fingerprint is the roster authority.
- Every decoded card must resolve to an exact CardID.
- Source claims keep their provenance and explicit `claim_kind`.
- Missing or weak strategic evidence remains visible and cannot be inferred
  from mana curve, card role, deck name, or generic gameplan text.

## Outputs

- `GlobalValues.json` is complete for its supported schema.
- `Mulligan.json` contains only explicitly authorized hand-required rules.
- Every decoded card has a per-card `<CARDID>.json` contract.
- `Combo.json` exists only for exact ordered combo evidence with the required
  live-verified strategic authority.
- `reports/operator_summary.json` is the sole normal apply authority.

`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are not normal
HSConfig output surfaces. Their absence does not block a valid load-safe
package; their presence in a normal package is drift.

## Completion boundary

Repository fixtures, generated contracts, CI, and documentation can prove
pre-run structural and semantic checks. They do not prove in-client loading,
runtime sampling, patch correctness, gameplay improvement, or post-game tuning.
Those outcomes remain `OUT_OF_SCOPE_ASSUMED_EXTERNAL` until separately observed
by the responsible external system.

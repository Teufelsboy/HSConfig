# Kingslayer Quick Pick Source Decision

This page records the current HSConfig decision for `Kingslayer` and `DEEP_014` / `Quick Pick`.

## Decision

Keep `Kingslayer` as `source_informed_valid_fixture`.

Do not promote Kingslayer to `core_source_backed_fixture` unless an exact source explicitly says whether `DEEP_014` / `Quick Pick` should be kept or discarded in the mulligan for the provided Kingslayer deck, or for a directly matching Kingslayer/Kingsbane weapon rogue list that includes `DEEP_014` / `Quick Pick`.

## Stop Condition

`exact_kingslayer_quick_pick_mulligan_source_unavailable`

## Why

The current Kingslayer fixture can produce a valid source-informed package, but `DEEP_014` / `Quick Pick` is still the first missing source-depth chain.

The checked Kingslayer deck context publicly lists `Quick Pick`, but does not expose an explicit card-level mulligan keep/discard instruction. Adjacent archetype advice is not source-backed evidence for this representative row unless it is directly about a matching Kingslayer/Kingsbane weapon rogue list that includes `Quick Pick`.

## Source-Backed Strong Promotion Rule

Kingslayer can move to `core_source_backed_fixture` only when a fixture prepare run proves all six checks:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- zero semantic blockers
- zero blocked cards in `source_claim_gap_report.json`
- no generated `Presume.json` or `Concede.json`

## Current Operator Action

Preserve this row as a visible source-informed control until exact Quick Pick mulligan evidence exists.

Do not widen the matrix to a twelfth representative deck to avoid this row.

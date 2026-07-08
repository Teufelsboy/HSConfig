# Boarlock Fracking Source Decision

This page records the current HSConfig decision for `Boarlock` and `WW_092` / `Fracking`.

## Decision

Keep `Boarlock` as `source_informed_valid_fixture`.

Do not promote Boarlock to `core_source_backed_fixture` unless an exact Boarlock-relevant source explicitly says whether `WW_092` / `Fracking` should be kept or discarded in the mulligan.

Current stop condition:

`exact_boarlock_fracking_mulligan_source_unavailable`

## Why

The current Boarlock fixture contains a low-confidence mulligan row for `WW_092` / `Fracking`, but the evidence is generic card-draw advice rather than an exact Fracking keep-or-discard instruction.

Low-confidence generic card-draw advice is not enough for `SOURCE_BACKED_STRONG`.

Adjacent archetype advice is not enough for `SOURCE_BACKED_STRONG`.

The row must keep exposing:

- `technical_status=VALID_PACKAGE`
- `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`
- `first_missing_chain.card_id=WW_092`
- `first_missing_chain.name=Fracking`
- `first_missing_chain.first_missing_link=needs_mulligan_claim`
- `source_depth_lane=mulligan_claim_gap`

## Closure Routing

Boarlock remains the first closure-truth row because it is the representative `Combo.json` control.

After this explicit preservation decision, the next actionable closure target is:

`Kingslayer`

Next actionable closure target: `Kingslayer`

## Accepted Evidence

Accepted evidence for changing this decision must be all of:

- Boarlock-relevant.
- About the provided Boarlock-style combo/control shell.
- Explicit about `Fracking`.
- Explicit about mulligan keep or discard.
- Current enough to not contradict live Hearthstone card text or HearthstoneJSON metadata.

## Rejected Evidence

Rejected evidence:

- Generic "mulligan for card draw" statements.
- Adjacent archetype advice.
- Deck pages that list `Fracking` without mulligan instruction.
- Low-confidence source rows.
- Runtime logs, winrate, replay evidence, HDT evidence, or HSTuner output, because HSConfig is pre-run only.

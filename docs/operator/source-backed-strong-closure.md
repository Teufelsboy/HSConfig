# Source-Backed Strong Closure

This file tracks which representative HSConfig deck fixtures are truly strong.

For the promotion wave, check `reports/source_claim_gap_report.json` first for the first missing source or lowering link, then `reports/strong_promotion_report.json` for the promotion verdict.

`core_source_backed_fixture` means the fixture must produce:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- no `semantic_blockers`
- no normal-path `Presume.json` or `Concede.json`

`source_informed_valid_fixture` means the fixture proves a valid source-informed package,
but it still needs guide claims, runtime-surface lowering, condition lowering,
mechanic lowering, or combo sequence detail before it can be called strong.

The fixture matrix also documents `decision_families_proven` and `known_coverage_limits`. These fields describe what a fixture proves for HSConfig's pre-game config compiler. They are not gameplay-quality claims and they do not imply post-run optimization coverage.

## Promotion Rule

A matrix row may move from `source_informed_valid_fixture` to `core_source_backed_fixture` only when a fixture prepare run proves:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- zero semantic blockers
- zero blocked cards in `source_claim_gap_report.json`
- no generated `Presume.json` or `Concede.json`

Rows that do not meet all six checks stay source-informed and must expose one specific first missing chain.

## Current Closure Targets

| Deck | Fixture stage | Required work before promotion |
|---|---|---|
| ShadowPriest | `core_source_backed_fixture` | Already strong. Preserve this as the control fixture. |
| CtAPaladin | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture. |
| PirateRogue | `core_source_backed_fixture` | Already strong. Preserve this as the third promoted fixture. |
| BigShaman | `core_source_backed_fixture` | Already strong. Preserve the source-faithful recruit and deathrattle claim set, including explicit `9` recruit/big-cheat and `7` deathrattle runtime values. |
| Discolock | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture. |
| TreantDruid | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture. |
| ImbueMage | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture. |
| MechPala | `core_source_backed_fixture` | Already strong. Preserve this as the second promoted fixture. |
| Kingslayer | `source_informed_valid_fixture` | Promotion stays blocked: the exact provided Kingslayer deck page publicly lists `Quick Pick` but does not expose an explicit card-level mulligan instruction. The checked Kingsbane-specific mulligan post is for a different list without `Quick Pick`, and the only explicit `Quick Pick` mulligan statement found was for adjacent weapon rogue rather than the provided deck. |
| Boarlock | `source_informed_valid_fixture` | Preserved blocked: exact deck-specific Fracking mulligan evidence remains unavailable. The fixture still proves valid Combo.json generation, but it cannot be promoted while WW_092 lacks a keep/discard claim and runtime-surface blockers remain. |
| PirateDH | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture. |

## Current Source-Informed Closure Decisions

| Deck | Current decision | First missing link | Hard blocker reason |
|---|---|---|---|
| Kingslayer | Preserve as source-informed until blockers close | `DEEP_014` / Quick Pick needs explicit mulligan claim | `unsupported_conditions_present` |
| Boarlock | Preserve as source-informed until blockers close | `WW_092` / Fracking needs explicit mulligan claim | `cards_need_runtime_surface`, `generic_low_confidence_cards`, `uncovered_cards`, `unsupported_conditions_present` |

Do not widen the matrix to a twelfth deck to avoid these rows. Either close the first missing chain with deck-specific source evidence and runtime-surface lowering, or preserve the row as a visible source-informed control.

## Current Blocker Snapshot

Fresh local prepare runs for the current matrix state show:

| Deck | Semantic status | First missing chain | Next action |
|---|---|---|---|
| ShadowPriest | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| CtAPaladin | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| PirateRogue | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| BigShaman | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| Discolock | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| TreantDruid | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| ImbueMage | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| MechPala | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |
| Kingslayer | `VALID_BUT_NOT_GUIDE_STRONG` | `DEEP_014` `Quick Pick` -> `needs_mulligan_claim` | `add_mulligan_keep_or_discard_claim` |
| Boarlock | `VALID_BUT_NOT_GUIDE_STRONG` | `WW_092` `Fracking` -> `needs_mulligan_claim` | `add_mulligan_keep_or_discard_claim` |
| PirateDH | `SOURCE_BACKED_STRONG` | `none` | `READY_TO_APPLY_OR_HANDOFF` |

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

Runtime apply no longer requires every package to be `SOURCE_BACKED_STRONG`. The representative matrix still preserves source-strength truth, but `VALID_PACKAGE` plus `runtime_load_safe=true` is enough for an initial load-safe runtime write. Source-informed rows remain valuable because they expose confidence debt, not because they should block usable package handoff.

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
| Kingslayer | `source_informed_valid_fixture` | Preserved blocked with explicit stop condition: exact Kingslayer Quick Pick mulligan evidence remains unavailable. Preserve this row as the weapon-sequence source-informed control until an exact Kingslayer/Kingsbane Quick Pick keep-or-discard source exists. |
| Boarlock | `source_informed_valid_fixture` | Preserved blocked with explicit stop condition: exact Boarlock Fracking mulligan evidence remains unavailable or unresolved lowering blockers remain. Preserve this row as the combo-control source-informed control until those blockers close. |
| PirateDH | `core_source_backed_fixture` | Promotion proven. Keep as a core control fixture. |

- `Boarlock` remains source-informed with explicit stop condition `exact_boarlock_fracking_mulligan_source_unavailable` unless an exact Boarlock-relevant Fracking mulligan source is added.
- `Kingslayer` remains source-informed with explicit stop condition `exact_kingslayer_quick_pick_mulligan_source_unavailable` unless an exact Kingslayer/Kingsbane `DEEP_014` / `Quick Pick` mulligan source is added.
- Adjacent archetype advice is not source-backed evidence for these two rows.

## Current Source-Informed Closure Decisions

| Deck | Current decision | First missing link | Hard blocker reason |
|---|---|---|---|
| Kingslayer | Preserve as source-informed until exact source exists | `DEEP_014` / Quick Pick needs explicit mulligan claim | `unsupported_conditions_present`; stop condition `exact_kingslayer_quick_pick_mulligan_source_unavailable` |
| Boarlock | Preserve as source-informed until blockers close | `WW_092` / Fracking needs explicit mulligan claim | `cards_need_runtime_surface`, `generic_low_confidence_cards`, `uncovered_cards`, `unsupported_conditions_present` |

Boarlock's current low-confidence `WW_092` / `Fracking` mulligan row documents
generic card-draw advice only. Do not treat Boarlock's low-confidence Fracking row as SOURCE_BACKED_STRONG.

Current closure order is Boarlock first, Kingslayer second. Boarlock stays first
because it is the only representative `Combo.json` control row, but this row is
durably preserved as source-informed until exact Boarlock-relevant Fracking
mulligan evidence exists. Kingslayer follows because its remaining gap is
narrower and tied to `DEEP_014` / `Quick Pick`, but it is also preserved until
exact Quick Pick mulligan evidence exists.

After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target. The next closure target appears only when new exact source evidence is added for either preserved row or a future matrix row exposes a new first missing chain.

Do not widen the matrix to a twelfth deck to avoid these rows. Either close the first missing chain with deck-specific source evidence and runtime-surface lowering, or preserve the row as a visible source-informed control.

Supplemental proof decks live in `docs/operator/supplemental-proof-decks.json` and do not change the representative matrix count.

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

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

## Current Closure Targets

| Deck | Fixture stage | Required work before promotion |
|---|---|---|
| ShadowPriest | `core_source_backed_fixture` | Already strong. Preserve this as the control fixture. |
| MechPala | `core_source_backed_fixture` | Already strong. Preserve this as the second promoted fixture. |
| PirateRogue | `core_source_backed_fixture` | Already strong. Preserve this as the third promoted fixture. |
| CtAPaladin | `source_informed_valid_fixture` | Close guide-claim and recruit/board-flood runtime-surface gaps. |
| BigShaman | `core_source_backed_fixture` | Already strong. Preserve the source-faithful recruit and deathrattle claim set, including explicit `9` recruit/big-cheat and `7` deathrattle runtime values. |
| Discolock | `source_informed_valid_fixture` | Close guide-claim, discard runtime-surface, and mechanic-lowering gaps. |
| Kingslayer | `source_informed_valid_fixture` | Close guide-claim, weapon runtime-surface, and unsupported-condition gaps. |
| TreantDruid | `source_informed_valid_fixture` | Close guide-claim and token-board runtime-surface gaps. |
| ImbueMage | `source_informed_valid_fixture` | Close guide-claim, hero-power/spell-generation runtime-surface, and mechanic-lowering gaps. |
| Boarlock | `source_informed_valid_fixture` | Close guide-claim, combo/resource runtime-surface, and unsupported-condition gaps. |
| PirateDH | `source_informed_valid_fixture` | Close guide-claim and pirate/hero-attack runtime-surface gaps. |

## Current Blocker Snapshot

Fresh local prepare runs after the strict stage split show:

| Deck | Semantic status | Guide gaps | Runtime-surface gaps | Mechanic-lowering gaps |
|---|---|---:|---:|---:|
| ShadowPriest | `SOURCE_BACKED_STRONG` | 0 | 0 | 0 |
| CtAPaladin | `VALID_BUT_NOT_GUIDE_STRONG` | 4 | 4 | 0 |
| PirateRogue | `SOURCE_BACKED_STRONG` | 0 | 0 | 0 |
| BigShaman | `SOURCE_BACKED_STRONG` | 0 | 0 | 0 |
| Discolock | `VALID_BUT_NOT_GUIDE_STRONG` | 2 | 9 | 2 |
| TreantDruid | `VALID_BUT_NOT_GUIDE_STRONG` | 9 | 3 | 0 |
| ImbueMage | `VALID_BUT_NOT_GUIDE_STRONG` | 3 | 3 | 1 |
| MechPala | `SOURCE_BACKED_STRONG` | 0 | 0 | 0 |
| Kingslayer | `VALID_BUT_NOT_GUIDE_STRONG` | 7 | 2 | 0 |
| Boarlock | `VALID_BUT_NOT_GUIDE_STRONG` | 7 | 5 | 0 |
| PirateDH | `VALID_BUT_NOT_GUIDE_STRONG` | 10 | 2 | 0 |

# Source-Backed Strong Closure

This file tracks which representative HSConfig deck fixtures are truly strong.

`core_source_backed_fixture` means the fixture must produce:

- `technical_status=VALID_PACKAGE`
- `semantic_status=SOURCE_BACKED_STRONG`
- `next_action=READY_TO_APPLY_OR_HANDOFF`
- no `semantic_blockers`
- no normal-path `Presume.json` or `Concede.json`

`source_informed_valid_fixture` means the fixture proves a valid source-informed package,
but it still needs guide claims, runtime-surface lowering, condition lowering,
mechanic lowering, or combo sequence detail before it can be called strong.

## Current Closure Targets

| Deck | Fixture stage | Required work before promotion |
|---|---|---|
| ShadowPriest | `core_source_backed_fixture` | Already strong. Preserve this as the control fixture. |
| MechPala | `source_informed_valid_fixture` | Close guide-claim gaps. |
| PirateRogue | `source_informed_valid_fixture` | Close guide-claim gaps. |
| CtAPaladin | `source_informed_valid_fixture` | Close guide-claim and recruit/board-flood runtime-surface gaps. |
| BigShaman | `source_informed_valid_fixture` | Close guide-claim and big/recruit/deathrattle runtime-surface gaps. |
| Discolock | `source_informed_valid_fixture` | Close guide-claim, discard runtime-surface, and mechanic-lowering gaps. |
| Kingslayer | `source_informed_valid_fixture` | Close guide-claim, weapon runtime-surface, and unsupported-condition gaps. |
| TreantDruid | `source_informed_valid_fixture` | Close guide-claim and token-board runtime-surface gaps. |
| ImbueMage | `source_informed_valid_fixture` | Close guide-claim, hero-power/spell-generation runtime-surface, and mechanic-lowering gaps. |
| Boarlock | `source_informed_valid_fixture` | Close guide-claim, combo/resource runtime-surface, and unsupported-condition gaps. |
| PirateDH | `source_informed_valid_fixture` | Close guide-claim and pirate/hero-attack runtime-surface gaps. |

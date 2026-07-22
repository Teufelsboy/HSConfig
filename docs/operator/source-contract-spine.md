# Source Contract Spine

Diagnostic reference only.

`reports/operator_summary.json` remains the only normal apply authority.

This page explains why a source claim did or did not lower to runtime config. It is diagnostic context, not an apply authority.

## Normal Runtime Surfaces

| Surface | Use |
| --- | --- |
| `Mulligan.json` | Explicit opening-hand `mulligan_keep` and `mulligan_discard` claims only. |
| `GlobalValues.json` | Governed Step 1 posture overlays from `gameplan_posture`; numeric tuning waits for runtime evidence. |
| `Combo.json` | Explicit ordered `combo_sequence` claims only. |
| `CARDID.json` | Card-local behavior such as targeting, hero-power transform, option identity, and supported mechanic behavior. |

`Presume.json` and `Concede.json` are documented HearthRanger concepts but not normal HSConfig runtime outputs.

## Claim-Kind Spine

| Claim Kind | Lane | Runtime Surface | Boundary |
| --- | --- | --- | --- |
| `archetype` | report_only | none | Context only; not a runtime row. |
| `mulligan_keep` | runtime_lowerable | `Mulligan.json` | Requires explicit opening-hand keep intent. |
| `mulligan_discard` | runtime_lowerable | `Mulligan.json` | Requires explicit opening-hand discard intent. |
| `card_role` | suppressed_or_conditional | `CARDID.json` | Requires supported card behavior surface. |
| `targeting_rule` | runtime_lowerable | `CARDID.json` | Requires supported target and block identity. |
| `combo_sequence` | runtime_lowerable | `Combo.json` | Requires complete ordered sequence. |
| `gameplan_posture` | runtime_lowerable | `GlobalValues.json` | Posture overlay only; not numeric runtime tuning. |
| `hero_power_transform` | suppressed_or_conditional | `CARDID.json` | Preserves effect semantics; not a mulligan keep by itself. |
| `mechanic_usage` | suppressed_or_conditional | `CARDID.json` | Requires documented CardID surface. |
| `known_bad_pattern` | suppressed_or_conditional | `CARDID.json` | Requires supported negative behavior row. |
| `tech_slot` | report_only | none | Deck construction advice only. |
| `replacement_option` | report_only | none | Deck replacement advice only. |
| `discover_choice` | suppressed_or_conditional | `CARDID.json` | Requires exact Discover option identity. |
| `choose_one_choice` | suppressed_or_conditional | `CARDID.json` | Requires exact Choose One option identity. |
| `globalvalue_numeric_tuning` | runtime_evidence_required | none | Requires runtime evidence before numeric write. |

## False-Lowering Boundaries

- Start-of-game effects are not opening-hand mulligan keeps unless the source explicitly says to keep the card in the opening hand.
- Deckbuilding effects are contract evidence, not live runtime actions.
- Discover and Choose One claims need exact option identity before lowering.
- Generated random pools stay report-visible unless the generated entity is deterministic.
- Secret timing, location activation, weapon attack posture, Titan choices, Tourist deckbuilding, Imbue, Forge, Excavate, and unknown mechanics stay warning/report-first until a deterministic runtime mapping exists.

Warnings are follow-up work, not runtime apply blockers.

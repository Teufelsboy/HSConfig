# Universal Wild No-Block Contract

HSConfig must produce a load-safe initial HearthRanger CustomConfig package for
every valid deck input.

## Runtime Apply Promise

- `technical_status=VALID_PACKAGE` means the emitted package is structurally valid.
- `runtime_load_safe=true` means the package passed HSConfig's normal pre-run load-safety contract.
- `runtime_apply_mode=load_safe_apply` means normal `hsconfig apply --json` is allowed.
- `SOURCE_BACKED_STRONG` is a source-confidence label, not the runtime-write gate.
- `READY_TO_APPLY_WITH_WARNINGS` still means the package is usable.

Minimal load-safe runtime apply is deliberately narrower than normal prepare richness. `GlobalValues.json` and `Mulligan.json` are the required runtime files. Per-card `<CARDID>.json` files, `Combo.json`, and identity-gated option files make the package more useful, and normal deck preparation should emit them when the deck and evidence support them, but their absence alone must not block a package that is otherwise `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.

## Non-Blocking Config Usefulness

`config_usefulness` is descriptive. It must not change the no-block contract:

- `VALID_PACKAGE` remains the technical load-safety truth.
- `load_safe_apply` remains allowed when the apply gate is structurally valid.
- `config_usefulness.status=load_safe_but_thin` is a warning surface, not an apply blocker.
- `config_usefulness.next_report_to_open` tells the operator which pre-run report explains the first usefulness gap.

## Hard Blocks

HSConfig still blocks when it cannot produce a correct runtime package:

- malformed or unsupported deckcode
- unresolved exact deck-card identity needed for `<CARDID>.json`
- invalid JSON
- unsupported VisionAI filename or block
- missing `GlobalValues.json`, `Mulligan.json`, or required per-card CardID files
- undeclared runtime files
- nested runtime files
- normal-path `Presume.json` or `Concede.json`
- forged or stale apply evidence

## Non-Blocking Warnings

These stay visible, but they do not block a valid package:

- missing guide claims
- generic-low-confidence cards
- runtime-surface gaps that stay report-only
- unsupported semantic claims that are suppressed instead of emitted
- partial mechanic support
- warning-only mechanics

## Mechanic Support Levels

- `direct`: HSConfig can emit the documented normal-path runtime row.
- `identity_gated_direct`: HSConfig can emit the documented runtime row only when exact option or transformed-identity resolution is available.
- `partial`: HSConfig can emit only the parts that map to documented VisionAI blocks.
- `warning_only`: HSConfig must not invent a runtime row for the mechanic's signature action.

`mechanic_visibility_summary` is an operator-facing explanation layer. It is not an apply gate. Partial and warning-only mechanics are descriptive and must not block load-safe apply when `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.

`choose_one` is `identity_gated_direct`: HSConfig can lower it through `OnChooseOneCardBonus` only when exact option identity is source-backed. `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are `warning_only`: they are visible in `warning_boundaries`, but they must not block load-safe apply. `generated_entity` and its `spell_generation` alias stay in `partial`, because exact generated identity can be represented only when the generated card is known.

`generated_entity` and its `spell_generation` alias stay in `partial`; they are not identity-gated direct coverage.

Use `first_warning_boundary` for the first next-inspection item and
`warning_boundaries` for the complete alphabetical list of report-only mechanics.

## Proof Matrix

The universal matrix test covers:

- ShadowPriest
- CtAPaladin
- PirateRogue
- BigShaman
- Discolock
- TreantDruid
- ImbueMage
- MechPala
- Kingslayer
- Boarlock
- PirateDH
- CuteWarrior

Each deck must produce `VALID_PACKAGE`, `runtime_load_safe=true`,
`runtime_apply_mode=load_safe_apply`, `GlobalValues.json`, `Mulligan.json`, and
one per-card JSON file for every unique deck CardID.

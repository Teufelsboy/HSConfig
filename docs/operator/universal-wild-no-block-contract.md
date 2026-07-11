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
`Concede.json` is publicly documented as a HearthRanger VisionAI surface. `Presume.json` is publicly documented on HearthRanger's AOE play-around page for opponent hand-card assumptions, and normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
The proof-matrix expectation that normal `prepare` emits one per-card JSON file for every unique deck CardID is HSConfig rich-output repo policy. It is not the minimal runtime-apply gate and not an official HearthRanger minimum.

## Card Data Intake

HSConfig uses a three-layer intake policy:

- Layer 1: deck-card identity is gated through collectible deck-card metadata.
- Layer 2: directly referenced companion entities are enriched from full `cards.json` metadata when available.
- Layer 3: text-only or rule-only mechanics stay visible in mechanic-drift reports.

Layer 2 and Layer 3 gaps are warning-only. They must not block `load_safe_apply` when the package is otherwise `VALID_PACKAGE`.

## Non-Blocking Config Usefulness

`config_usefulness` is descriptive. It must not change the no-block contract:

- `VALID_PACKAGE` remains the technical load-safety truth.
- `load_safe_apply` remains allowed when the apply gate is structurally valid.
- `config_usefulness.status=load_safe_but_thin` is a warning surface, not an apply blocker.
- `config_usefulness.next_report_to_open` tells the operator which pre-run report explains the first usefulness gap.

## Hard Blocks

HSConfig still blocks when it cannot produce a correct runtime package:

- malformed or unsupported deckcode
- invalid JSON
- unsupported VisionAI filename or block
- missing required minimal runtime files: `GlobalValues.json` or `Mulligan.json`
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

## Failure Mode Summary

`reports/operator_summary.json` includes `no_block_failure_mode_summary`.
This is an explanatory summary, not a new permission model. It groups real
technical stops under `technical_hard_block` and non-blocking follow-up work
under `source_depth_warning`, `warning_only_mechanic`,
`future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and
`runtime_evidence_only_tuning`. It does not create a second apply gate.

Mechanic drift is not a runtime apply gate. `reports/mechanic_drift_report.json` and `mechanic_drift_summary` expose unknown mechanics, text-only mechanics, and unknown card types as warning data. Unknown mechanics are warning-only and do not block load-safe apply when `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.

Modern mechanic visibility is non-blocking. `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` are current/static mechanic visibility labels. They may lower as `partial` when HSConfig has a safe existing VisionAI posture surface, otherwise they stay `warning_only`.
`rewind`, `herald`, and `shatter` are warning-only report-only visibility labels; HSConfig names them in reports and does not map them to runtime surfaces. Neither state blocks `load_safe_apply` for a technically valid package.

## Mechanic Support Levels

- `direct`: HSConfig can emit the documented normal-path runtime row.
- `identity_gated_direct`: HSConfig can emit the documented runtime row only when exact option or transformed-identity resolution is available.
- `partial`: HSConfig can emit only the parts that map to documented VisionAI blocks.
- `warning_only`: HSConfig must not invent a runtime row for the mechanic's signature action.

`mechanic_visibility_summary` is an operator-facing explanation layer. It is not an apply gate. Partial and warning-only mechanics are descriptive and must not block load-safe apply when `technical_status=VALID_PACKAGE` and `runtime_apply_mode=load_safe_apply`.

The mechanic lowering registry is the executable authority behind `needs_mechanic_lowering`. `cards_needing_mechanic_lowering` only increments when a registered mechanic has a documented default CardID lowering target and no meaningful CardID row was emitted. Dredge, Tradeable, and unknown future mechanics stay report-only/warning-only; they do not increment `cards_needing_mechanic_lowering`.

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
`runtime_apply_mode=load_safe_apply`, `GlobalValues.json`, and `Mulligan.json`.
As HSConfig rich-output repo policy, normal `prepare` must also emit one per-card
JSON file for every unique deck CardID when deck-card identity is known. That
rich-output proof is not the minimal runtime-apply gate.

Supplemental visibility decks may broaden Wild mechanic coverage without
becoming representative source-depth rows. They must still obey the same
runtime promise: a valid package remains `load_safe_apply`, warning-only
mechanics stay descriptive, and normal output must not emit `Presume.json` or
`Concede.json`.

## Acceptance Matrix Diagnostic

`hsconfig acceptance-matrix` may summarize prepared packages across the proof
set. This command is a read-only diagnostic surface for package status,
runtime-file coverage, CardID file counts, and warning boundaries.
It does not change the apply gate. Runtime permission still comes only from
`reports/operator_summary.json` and the guarded `hsconfig apply` path.

The matrix-level `status` is the diagnostic authority for the matrix output.
Per-row fields are intentionally verbose so a failed matrix can still show
which lower-level checks were already true. Detail fields never override
`status` or `matrix_row_status`.

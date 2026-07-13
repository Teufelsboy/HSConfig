# HSConfig Operator Guide

HSConfig creates pre-game HearthRanger VisionAI `CustomConfig` packages from a deck name, deck code, and source-backed guide evidence.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

Research artifacts are evidence, not operator instructions. Use `docs/research/README.md` when auditing why a source-depth or fixture decision exists; return to this guide for the normal command path.

Runtime Mulligan writes require explicit `claim_kind` values such as `mulligan_keep` or `mulligan_discard`. Card importance, start-of-game effects, deckbuilding effects, hero-power-transform text, and guide gameplan text remain contract evidence unless they are separately backed by explicit hand-required Mulligan guidance.
Effect semantics are not opening-hand mulligan keeps: start-of-game and deckbuilding cards can stay visible in card behavior or diagnostics while remaining absent from `Mulligan.json`.

### Source claim vs runtime surface

`claim_kind` describes what the source says. It does not by itself authorize a
runtime write. Runtime output is decided by surface-specific gates:

- `Mulligan.json`: only explicit `mulligan_keep` or `mulligan_discard` claims.
- `GlobalValues.json`: curated `gameplan_posture` overlays plus full baseline keys.
- `Combo.json`: exact `combo_sequence` claims with valid CardID sequences.
- `<CARDID>.json`: documented CardID behavior claims such as targeting,
  mechanic usage, hero-power transform, discover, choose-one, and known bad
  patterns.

Wrong-surface or low-confidence claims do not block deck generation. They are
reported as suppressed/report-only rows with explicit reasons.
`reports/source_contract_audit.json` explains those source-to-runtime decisions
per claim and per card; it does not replace `reports/operator_summary.json`.
`source_contract_audit.json` is diagnostic. Its `claim_lifecycle_rows` explain
source -> policy -> surface gate -> builder/router -> emitted/suppressed.
Runtime readiness still comes from `operator_summary.json`.
`reports/source_to_runtime_explainability.json` is the card-readable projection
of that audit: it names emitted runtime files, missing runtime files, the first
missing link, and the next source action per claim/card. Its compact
`source_to_runtime_explainability_summary` in `operator_summary.json` is
non-blocking and does not grant apply permission.

Source-contract invariant: effect semantics are preserved on supported effect
and CardID surfaces, but only exact runtime-surface claims lower into matching
runtime JSON. Start-of-game, deckbuilding, deck-state, and hero-power-transform
facts do not become Mulligan keeps unless there is separate exact hand-keep
authority. `source_contract_audit.json` is diagnostic; `operator_summary.json`
remains the normal apply authority.

`operator_summary.json` remains the only normal apply authority.
`source_contract_audit.json` explains why each claim did or did not lower.
`contract_spine_rows` show the compact source -> policy -> surface gate -> builder/router -> runtime effect chain.
Warnings are follow-up work, not a runtime apply blocker.
Do not use `source_contract_audit.json` as an apply gate.

## Quick Start

- Run `hsconfig configure` for normal operation.
- Open `reports/operator_summary.json` first.
- `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` means runtime apply is allowed.
- Warnings are follow-up work, not a second apply gate.
- HSTuner owns post-run evaluation and tuning.

## Preferred Normal Path

Preferred normal path: `hsconfig configure`.

Use `hsconfig configure` for normal operation:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json
```

This command runs the lower-level pre-run chain, writes a validated package, and leaves the final decision in `outputs/<DeckName>/04_package/reports/operator_summary.json`.

For staged inspection, use the Lower-Level Inspected Path below.
Per-card runtime files use `per-card <CARDID>.json` naming when the guide-backed surface is documented.
Choice surface lowering follows the card behavior policy: `discover_choice` and `choose_one_choice` only lower when option identity is source-backed, and unresolved identities stay in `card_behavior_suppression_report.json`.

## Normal Operator Path

1. Run `hsconfig configure --deck-name <deck> --deck-code <code> --runtime-root <runtime-root> --out <out> --json`.
2. Add `--source-evidence-json <file>` when current guide evidence rows are already available.
3. Open `reports/operator_summary.json` first.
4. Run `hsconfig apply` only when the operator summary allows it, or use `hsconfig configure --apply` when the same guarded apply should happen in the configure run.

Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.

## Lower-Level Inspected Path

Lower-level inspected path: `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`.

Use this path when each source and research stage must be inspected before package preparation.

1. Run `hsconfig source-manifest` to get aliases, card targets, and research questions.
2. Write short source evidence rows from current guide, archetype, mulligan, card-text, and metadata sources.
3. Run `hsconfig draft-source-documents` to turn evidence rows into strict `source_documents.json`.
4. Run `hsconfig research-deck --source-documents-json ...` to normalize guide sources.
5. Run `hsconfig prepare --guide-sources-json ...` to compile the pre-run package and reports.
6. Run `hsconfig validate --package <package> --json` before handoff or runtime apply.
7. Open `reports/operator_summary.json` first.
8. Run `hsconfig apply` only when the operator summary allows it.

## Load Safety vs. Config Richness

Open `reports/operator_summary.json` first.

- `technical_status`, `runtime_apply_mode`, and `runtime_apply_allowed` decide whether the package is structurally load-safe to apply.
- Minimal load-safe apply requires `GlobalValues.json` and `Mulligan.json`. Normal `prepare` packages should still emit per-card `<CARDID>.json` files when deck-card identity is known, but those rich CardID files are not the minimal runtime-apply gate.
- `Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path; their absence never blocks a valid load-safe package.
- `load_safe_apply` is an HSConfig operator policy, not a HearthRanger public-doc term. per-card-every-card coverage is HSConfig rich output for stronger control and matrix proof, not a minimal runtime-write requirement.
- `config_usefulness` is non-blocking. It explains whether the load-safe package is guide-aligned, usable with targeted gaps, or load-safe but thin.
- `config_usefulness.surfaces.mulligan` separates runtime load safety from Mulligan richness. A present `Mulligan.json` can satisfy the load-safe gate while `status=thin`, `first_gap_reason`, or `next_source_need=source_backed_mulligan_keeps` tells the operator that more guide-backed keep/discard evidence would improve the package.
- `mechanic_visibility_summary` is descriptive and non-blocking. It shows `direct`, `identity_gated_direct`, `partial`, and `warning_only` mechanic buckets so a valid package can be applied while still making Dredge, Tradeable, unresolved generation, or partial targeting limits visible.

The mechanic lowering registry is the executable authority behind `needs_mechanic_lowering`. `cards_needing_mechanic_lowering` only increments when a registered mechanic has a documented default CardID lowering target and no meaningful CardID row was emitted. Dredge, Tradeable, and unknown future mechanics stay report-only/warning-only; they do not increment `cards_needing_mechanic_lowering`.

`first_warning_boundary` names the first next-inspection item. `warning_boundaries` is the complete alphabetical list of report-only mechanics the operator may inspect next. `choose_one` is identity-gated direct, while `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only. These warnings are explanatory; warning-only mechanics do not block load-safe apply for a valid package.

`reports/mechanic_drift_report.json` is the non-blocking current-card-data drift surface. `mechanic_drift_summary` in `reports/operator_summary.json` lists unknown mechanics, text-only mechanics, and unknown card types detected from HearthstoneJSON-style metadata. Unknown mechanics are warning-only and do not block load-safe apply. Mechanic drift is not a runtime apply gate; it tells the operator which future Wild mechanic should be mapped next.

Modern mechanic visibility is non-blocking. HSConfig names current mechanics such as `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` when card metadata or text exposes them. Mechanics without a documented normal-path VisionAI runtime surface stay visible as `warning_only` or `partial`; they must not block `load_safe_apply` for a technically valid package.
`rewind`, `herald`, and `shatter` are warning-only report-only visibility labels; HSConfig names them in reports and does not map them to runtime surfaces.

- Open `reports/semantic_enrichment_report.json` when the summary points to static or warning-only mechanic coverage. It explains inferred card semantics, static evidence, linked entities, deckwide effects, and warning-only flags. Lowerability buckets live in `reports/operator_summary.json` and `reports/per_card_config_readiness_report.json`.
- A thin package may still be applied. Thin means the operator should inspect the named `next_report_to_open`, not that HSConfig should stop.
- A thin Mulligan means guide evidence did not name enough explicit `mulligan_keep` or `mulligan_discard` claims. It is a source-quality signal, not a HearthRanger load error, and HSConfig does not invent opening-hand holds from card importance or early-role hints.
- HSConfig stays pre-run only. Post-game evidence review and post-game tuning belong in HSTuner, outside this skill.

## Single Gate

Use `reports/operator_summary.json` as the normal operator gate.

`no_block_failure_mode_summary` is the fastest way to read why a package did
or did not stop. `technical_hard_block` is the only hard stop category. The
other categories, `source_depth_warning`, `warning_only_mechanic`,
`future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and
`runtime_evidence_only_tuning`, explain source or semantic limits while
`load_safe_apply` can still proceed for `technical_status=VALID_PACKAGE`.
It does not create a second apply gate.

`hsconfig apply --fake --json` creates a receipt-bound preview without runtime mutation.
Normal `hsconfig apply --json` remains autonomous when the gate allows it: it creates
and verifies the fake receipt in the same invocation, then writes the runtime package.
`--from-fake-receipt` can be used when an operator wants to apply a previously generated
matching fake receipt.

For the durable no-block contract across valid Wild decks, see
`docs/operator/universal-wild-no-block-contract.md`.

- `technical_status=VALID_PACKAGE` means the runtime JSON shape is structurally valid and load-safe.
- `runtime_load_safe=true` means the package passed the normal pre-run load-safety contract.
- `runtime_apply_mode=load_safe_apply` means normal `hsconfig apply --json` is allowed.
- `runtime_apply_mode=blocked` means no runtime write should happen because the package is invalid or load-unsafe.
- `runtime_apply_allowed=true` is descriptive; the CLI and `apply_package()` still re-evaluate the gate before writing.
- `semantic_status=SOURCE_BACKED_STRONG` means source coverage and per-card closure support source-backed confidence and handoff. It is not a runtime apply permission; use `technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` for normal guarded apply.
- `semantic_status=VALID_BUT_NOT_GUIDE_STRONG` means the package is valid and load-safe, but source depth, runtime surfaces, combo detail, conditions, mechanics, or conflicts still need work before it can be called source-backed strong.
- `apply_policy=ALLOWED` marks the no-warning source-strong path; it is not the only normal apply permission.
- `next_action=READY_TO_APPLY_WITH_WARNINGS` plus `apply_policy=ALLOWED_WITH_WARNINGS` means the package is still allowed to write at runtime when `technical_status=VALID_PACKAGE`, while semantic warnings remain visible in the reports.
- `source_informed_apply_readiness.status=ready` is diagnostic only. It documents that the remaining semantic blockers are limited to allowed source-depth gaps such as `cards_need_guide_claims` or `cards_need_mulligan_claims`.
- `cards_need_runtime_surface`, combo, condition, mechanic, conflict, unsupported-condition, uncovered-card, and generic-low-confidence blockers keep source-informed apply blocked.
- `ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE`; warnings describe semantic/source confidence debt, not a write blocker.

Lower-level reports explain the gate. They do not grant independent apply permission.

Direct Python runtime writes use the same gate. `hsconfig.runtime_apply.apply_package()` resolves `reports/operator_summary.json` through `evaluate_apply_gate()` before any runtime mutation and rejects forged or missing gate dictionaries. Use the CLI for normal operation; direct imports are test and integration surfaces, not a second permission model.

## Report Ownership

Open `reports/operator_summary.json` first. Lower-level reports explain the gate. They do not grant independent apply permission.

`source_depth_lane` is a readable alias for the first missing source/runtime link:
`closed`, `source_claim_gap`, `mulligan_claim_gap`, `runtime_surface_gap`,
`combo_sequence_gap`, `condition_lowering_gap`, or `mechanic_lowering_gap`.
It does not grant apply permission. Use `reports/operator_summary.json` as the gate.

| File | Authority | Answers |
| --- | --- | --- |
| `reports/operator_summary.json` | normal operator gate | what to do next |
| `reports/source_to_runtime_explainability.json` | diagnostic source-to-runtime projection | which exact source-to-runtime link is missing before a card can be stronger |
| `reports/source_contract_audit.json` | diagnostic source-to-runtime explanation | why each source claim did or did not lower to runtime config |
| `reports/source_claim_gap_report.json` | repair contract | which card link is missing first |
| `reports/strong_promotion_report.json` | promotion confirmation | whether the package can be called source-backed strong |
| `reports/per_card_config_readiness_report.json` | card lane diagnostics | which lane each card occupies |
| `reports/guide_source_depth_report.json` | source-depth diagnostics | how strong the guide and source coverage is |
| `reports/global_values_authority_matrix.json` | GlobalValues diagnostics | which GlobalValues keys are source-backed or archetype-inferred |
| `reports/mechanic_drift_report.json` | non-blocking mechanic drift visibility | which unknown, text-only, or current-card-type mechanics should be inspected next |
| `reports/semantic_enrichment_report.json` | semantic mechanic diagnostics | which static mechanics, linked entities, deckwide effects, and warning-only flags were inferred |

## Optional Acceptance Matrix

Use `hsconfig acceptance-matrix` after one or more packages have already been
prepared when you want a compact read-only proof view.

```powershell
hsconfig acceptance-matrix --package outputs/ShadowPriest --package outputs/BigShaman --json
```

The matrix summarizes `technical_status`, `runtime_apply_mode`, runtime file
coverage, CardID file count, `config_usefulness`, and warning boundaries across
packages. It is diagnostic only. It does not write runtime files, and it does not replace `reports/operator_summary.json`
as the single operator gate.

Read `status` first. The matrix-level `status` is authoritative for the
matrix diagnostic. Row fields such as `apply_gate_allowed`,
`runtime_apply_mode`, and `validation_status` explain why a package passed or
failed, but they do not override `status` or `matrix_row_status`.

Developer drift check: `hsconfig contract-spine-sentinel --json` verifies that source-contract diagnostics have not become a second apply gate. Normal deck configuration still starts with `hsconfig configure`, and `reports/operator_summary.json` remains the apply authority.

## Optional Contract Doctor

Use `hsconfig contract-doctor --package <package> --json` when a prepared package
is valid but you want a compact explanation of source -> claim_kind -> surface
gate -> builder/router -> runtime effect diagnostics. It does not write runtime
files; `--out` only writes the requested Markdown diagnostic.
operator_summary.json remains the only normal apply authority.

## Expert Paths

Use `hsconfig build`, `hsconfig research-contract`, `--cards-json`, `--claims-json`, `--plan-reports-dir`, and `--allow-placeholder` only for fixtures, diagnostics, or inspected expert inputs.

`--allow-source-informed` is backward-compatible. It is no longer required for a load-safe valid package. Use `reports/operator_summary.json` to distinguish load safety from semantic strength: `SOURCE_BACKED_STRONG` means high-confidence source-backed handoff, while `READY_TO_APPLY_WITH_WARNINGS` means the package is usable but still has documented confidence gaps.

```powershell
hsconfig apply --package <package> --runtime-root <runtime-root> --json
```

Source-informed apply is still not `SOURCE_BACKED_STRONG`; close the remaining `source_claim_gap_report.json` links before promoting the fixture or calling the package strong.

## Fixture Matrix

`docs/operator/archetype-fixture-matrix.json` is the representative 11-deck HSConfig proof set.

Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link. Close existing matrix gaps before adding more representative decks.

When a source-informed row cannot be promoted honestly, keep it visible with an explicit stop condition instead of widening the matrix or forcing a weak source claim.

Do not add a new representative deck when an existing row can exercise the same source-depth or runtime-surface family.

Boarlock remains the first closure-truth row because it is the representative
`Combo.json` control. Its current Fracking row is durably preserved as
source-informed until exact Boarlock-relevant Fracking mulligan evidence exists.

Boarlock and Kingslayer are both durable source-informed controls with explicit
stop conditions. Do not widen the representative matrix to a twelfth deck to
avoid these rows. Add or promote only when exact source evidence closes a
preserved stop condition.

After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target.

The representative fixture matrix proves source-depth breadth. The universal
no-block matrix proves the separate runtime promise: every valid listed deck
still creates a load-safe initial package even when source confidence remains
warning-only.

## Supplemental Proof Decks

`docs/operator/supplemental-proof-decks.json` lists decks that prove narrow command,
syntax, or acceptance behavior without widening the representative matrix.

CuteWarrior is supplemental. It must not be counted as a twelfth representative
row unless a future matrix review proves a real missing family that none of the
current eleven representative rows can exercise.

SecretMage and HighlanderPriest are supplemental visibility-only decks. They
prove that current Wild secret/highlander/location control surfaces still
produce load-safe packages, but they do not widen the representative matrix and
do not close Boarlock or Kingslayer source-depth stop conditions.

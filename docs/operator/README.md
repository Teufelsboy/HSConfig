# HSConfig Operator Guide

HSConfig creates pre-game HearthRanger VisionAI `CustomConfig` packages from a deck name, deck code, and source-backed guide evidence.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

Research artifacts are evidence, not operator instructions. Use `docs/research/README.md` when auditing why a source-depth or fixture decision exists; return to this guide for the normal command path.
The normal path is: source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply.
Per-card runtime files use `per-card <CARDID>.json` naming when the guide-backed surface is documented.
Choice surface lowering follows the card behavior policy: `discover_choice` and `choose_one_choice` only lower when option identity is source-backed, and unresolved identities stay in `card_behavior_suppression_report.json`.

## Normal Operator Path

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
- `config_usefulness` is non-blocking. It explains whether the load-safe package is guide-aligned, usable with targeted gaps, or load-safe but thin.
- `mechanic_visibility_summary` is descriptive and non-blocking. It shows `direct`, `identity_gated_direct`, `partial`, and `warning_only` mechanic buckets so a valid package can be applied while still making Dredge, Tradeable, unresolved generation, or partial targeting limits visible.

`first_warning_boundary` names the first next-inspection item. `warning_boundaries` is the complete alphabetical list of report-only mechanics the operator may inspect next. `choose_one` is identity-gated direct, while `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only. These warnings are explanatory; warning-only mechanics do not block load-safe apply for a valid package.
- Open `reports/semantic_enrichment_report.json` when the summary points to static or warning-only mechanic coverage. It explains inferred card semantics, static evidence, linked entities, deckwide effects, and warning-only flags. Lowerability buckets live in `reports/operator_summary.json` and `reports/per_card_config_readiness_report.json`.
- A thin package may still be applied. Thin means the operator should inspect the named `next_report_to_open`, not that HSConfig should stop.
- HSConfig stays pre-run only. Post-game evidence review and post-game tuning belong in HSTuner, outside this skill.

## Single Gate

Use `reports/operator_summary.json` as the normal operator gate.

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
- `semantic_status=SOURCE_BACKED_STRONG` means source coverage and per-card closure are strong enough for normal apply or handoff.
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
| `reports/source_claim_gap_report.json` | repair contract | which card link is missing first |
| `reports/strong_promotion_report.json` | promotion confirmation | whether the package can be called source-backed strong |
| `reports/per_card_config_readiness_report.json` | card lane diagnostics | which lane each card occupies |
| `reports/guide_source_depth_report.json` | source-depth diagnostics | how strong the guide and source coverage is |
| `reports/global_values_authority_matrix.json` | GlobalValues diagnostics | which GlobalValues keys are source-backed or archetype-inferred |
| `reports/semantic_enrichment_report.json` | mechanic inference diagnostics | which static mechanics, linked entities, deckwide effects, and warning-only flags were inferred |

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

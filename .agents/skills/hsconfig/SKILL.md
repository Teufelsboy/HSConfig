---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name and deck code. Use when Codex must build or validate direct Mulligan, GlobalValues, `per-card <CARDID>.json`, or Combo runtime config before games are played.
---

# HSConfig

Use this skill when Codex must create or validate a pre-game HearthRanger VisionAI `CustomConfig` package from a deck name, deck code, and current guide-backed research. HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

That pre-run boundary is repeated in the rules below for operators and tests.

For the normal operator entry point, start at `docs/operator/README.md`.

Inputs:

- deck name
- deck code
- runtime root for `prepare`, `build`, and `apply`
- short source evidence rows from current guide research
- researched `source_documents.json`
- normalized guide sources from `hsconfig research-deck`

Normal workflow:

1. Decode the deck code first, then resolve deck identity and card metadata.
2. Run `hsconfig source-manifest ...` to produce deck aliases, card targets, and research questions.
3. Research current guide, archetype, mulligan, card-text, and metadata sources as short evidence rows.
4. Run `hsconfig draft-source-documents ...` to create `source_documents.json` with card-specific claims.
5. Run `hsconfig research-deck --source-documents-json ...` to create normalized guide sources and the research contract inputs.
6. Run `hsconfig prepare --guide-sources-json ...` to compile the package and reports.
7. Read `reports/operator_summary.json` first and inspect `config_usefulness`, then inspect the research contract, `claim_coverage_report.json`, `source_claim_gap_report.json`, `strong_promotion_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, `global_values_authority_matrix.json`, `per_card_config_readiness_report.json`, and `guide_source_depth_report.json`.
8. Run `hsconfig apply ...` only when runtime writes are intended. Guarded apply stays pre-run: runtime writes remain only when requested through `hsconfig apply`. A package with `technical_status=VALID_PACKAGE`, `runtime_load_safe=true`, and `runtime_apply_mode=load_safe_apply` can be applied with `hsconfig apply --package <package> --runtime-root <runtime-root> --json`. `SOURCE_BACKED_STRONG` is a confidence label, not the default runtime-write gate.
9. Use `reports/operator_summary.json` as the single operator gate. Detail reports are evidence, not independent apply permissions.

Status meaning:

- `VALID_PACKAGE`: runtime JSON is structurally valid and load-safe.
- `SOURCE_BACKED_STRONG`: current guide-backed per-card coverage supports a strong initial config.
- `STATIC_SEMANTICS_USABLE`: static card semantics produced a valid package without enough live guide depth.
- `VALID_BUT_NOT_GUIDE_STRONG`: the package is valid, but `guide_strength_summary` and `semantic_blockers` identify missing source depth, conflict resolution, runtime-surface gaps, or combo detail.
- `SOURCE_INFORMED_APPLY_READY`: legacy compatibility status for older summaries that still require the narrow source-informed expert lane. Normal load-safe runtime apply is `READY_TO_APPLY_WITH_WARNINGS` / `ALLOWED_WITH_WARNINGS` when `technical_status=VALID_PACKAGE`; source-informed compatibility is still not `SOURCE_BACKED_STRONG`.

Fixture stage meaning:

- `core_source_backed_fixture`: the fixture must produce `SOURCE_BACKED_STRONG` in `operator_summary.json`.
- `source_informed_valid_fixture`: the fixture produces a valid package, but still has source-depth or lowering gaps before it can be called strong.
- `future_fixture`: reserved for examples outside the current proof set.

Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link, and operators should close existing matrix gaps before adding more representative decks.
`source_depth_lane` is the readable alias for that first missing source-to-runtime link. It helps operators read closure depth, but it is not an apply permission; keep `reports/operator_summary.json` as the single operator gate.
Current closure truth is Boarlock first, Kingslayer second. Boarlock stays first
because it is the only representative `Combo.json` control row, but its current
Fracking source is durably preserved as source-informed unless exact
Boarlock-relevant Fracking mulligan evidence appears.
Kingslayer is also durably preserved as source-informed unless exact Kingslayer/Kingsbane `DEEP_014` / `Quick Pick` mulligan evidence appears.
After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target.

Rules:

- Build direct guide-aligned configs only.
- Prefer researched guide sources over legacy claim inputs when live guide research was performed.
- Use `operator_summary.json` as the operator-facing readiness file and single operator gate; do not confuse `semantic_status` with runtime validity.
- Runtime apply is guarded.
- Read `runtime_load_safe`, `runtime_apply_mode`, `runtime_apply_allowed`, and `runtime_apply_requires_flag` in `operator_summary.json`. ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE; warnings describe semantic/source confidence debt.
- Inspect `mechanic_visibility_summary` in `reports/operator_summary.json` to understand direct, identity-gated direct, partial, and warning-only mechanic coverage. Treat warning-only mechanics as descriptive; warning-only mechanics do not block load-safe apply.
- Use `first_warning_boundary` in `mechanic_visibility_summary` as the first next-inspection item. Use `warning_boundaries` for the complete alphabetical list of report-only mechanics. `choose_one` is identity-gated direct; `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only and must not block load-safe apply.
- Open `reports/semantic_enrichment_report.json` when static or warning-only mechanic coverage needs explanation. It is a diagnostic report for inferred Hearthstone mechanics, linked entities, deckwide effects, and warning-only flags, not an independent apply gate. Lowerability buckets live in `reports/operator_summary.json` and `reports/per_card_config_readiness_report.json`.
- After `prepare`, inspect `config_usefulness` in `reports/operator_summary.json`.
- Treat `config_usefulness` as non-blocking: it describes richness across Mulligan, GlobalValues, CardID behavior, and Combo, but it must not prevent load-safe apply.
- If `config_usefulness.status` is `load_safe_but_thin` or `usable_with_targeted_gaps`, report the first gap and `next_report_to_open`; do not switch to HSTuner or replay analysis inside HSConfig.
- Runtime apply is always governed by `reports/operator_summary.json`; `apply_package()` and `hsconfig apply` must reject missing, blocked, or forged apply gates before writing HearthRanger runtime files.
- Keep exact CardID identity, full `GlobalValues` coverage, and the profile report.
- Keep the pre-run boundary visible in operator-facing copy and tests.
- Choice-surface lowering for `discover_choice` and `choose_one_choice` is source-backed only: lower only when option identity is resolved from source evidence and linked entity metadata; otherwise keep the suppression report visible.
- Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.
- Do not emit `Presume.json` or `Concede.json` in the normal path; they are legacy/gated surfaces only.
- Tell the user whether the package is guide-backed, static-semantics-backed, or still needs more research.

## Expert Paths

Use optional expert `--cards-json`, legacy `--claims-json`, or inspected `--plan-reports-dir` only for fixtures, diagnostics, or inspected expert inputs.
Use `--allow-placeholder` only for deterministic fixture or preview tests.

## References

- `references/workflow.md`
- `references/visionai-surfaces.md`
- `references/guide-research-policy.md`
- `references/globalvalues-policy.md`
- `references/card-behavior-policy.md`

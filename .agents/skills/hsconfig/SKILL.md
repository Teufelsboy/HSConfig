---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name and deck code. Use when Codex must build or validate direct Mulligan, GlobalValues, `per-card <CARDID>.json`, or Combo runtime config before games are played.
---

# HSConfig

Use this skill when Codex must create or validate a pre-game HearthRanger VisionAI `CustomConfig` package from a deck name, deck code, and current guide-backed research. HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

For the normal operator entry point, start at `docs/operator/README.md`.

Preferred normal path: `hsconfig configure`.

Lower-level inspected path: source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply.

Inputs: deck name, deck code, runtime root for `prepare`, `build`, and `apply`, short source evidence rows from current guide research, optional researched `source_documents.json`, and normalized guide sources from `hsconfig research-deck`.

Normal workflow:

1. Prefer `hsconfig configure ...` for normal operation.
2. Use lower-level commands only when inspecting a stage:
   `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`.
3. Open `reports/operator_summary.json` first.

Operator rules:

- Decode the deck code first, then resolve exact CardID identity before writing config.
- `hsconfig configure` is the normal one-command path; `source-manifest`, `draft-source-documents`, `hsconfig research-deck --source-documents-json`, and `hsconfig prepare --guide-sources-json` are inspected stages for fixtures, debugging, and research contract review.
- Use `reports/operator_summary.json` as the single operator gate. `VALID_PACKAGE` is runtime validity; `SOURCE_BACKED_STRONG`, `STATIC_SEMANTICS_USABLE`, and `VALID_BUT_NOT_GUIDE_STRONG` are confidence and source-depth labels.
- Runtime apply is guarded; runtime writes remain only when requested through `hsconfig apply` or `hsconfig configure --apply`; guarded apply validates `operator_summary.json`, package structure, fake receipts, and package hashes before writing.
- Read `runtime_load_safe`, `runtime_apply_mode`, `runtime_apply_allowed`, `runtime_apply_requires_flag`, and `apply_policy`. `ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE`; warnings describe source or semantic debt.
- Minimal `load_safe_apply` requires `GlobalValues.json` and `Mulligan.json`. `per-card <CARDID>.json` files and `Combo.json` are HSConfig rich-output repo policy, not the minimal runtime-write gate and not an official HearthRanger minimum.
- `Concede.json` is publicly documented. `Presume.json` is publicly documented on HearthRanger's AOE play-around page, and normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.
- `load_safe_apply` is an HSConfig operator policy, not a HearthRanger public-doc term.
- Inspect `config_usefulness`, `load_safe_but_thin`, `usable_with_targeted_gaps`, `next_report_to_open`, `mechanic_visibility_summary`, `mechanic_drift_summary`, `reports/mechanic_drift_report.json`, `reports/semantic_enrichment_report.json`, and `no_block_failure_mode_summary` when a package has warnings. warning-only mechanics do not block load-safe apply, and this does not create a second apply gate.
- `technical_hard_block` stops apply. `source_depth_warning`, `warning_only_mechanic`, `future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and `runtime_evidence_only_tuning` are follow-up labels.
- The mechanic lowering registry is the executable authority behind `needs_mechanic_lowering`: `cards_needing_mechanic_lowering` only increments when a registered mechanic has a documented default CardID lowering target and no meaningful CardID row was emitted. Dredge, Tradeable, and unknown future mechanics stay report-only/warning-only and do not increment `cards_needing_mechanic_lowering`.
- Modern mechanic visibility is non-blocking. `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` should be named in reports when detected, but they must not block load-safe apply unless the package is technically invalid.
- `rewind`, `herald`, and `shatter` are warning-only report-only visibility labels. Name them in reports when detected; normal HSConfig does not map them to runtime surfaces, and they must not block load-safe apply.
- Use `first_warning_boundary` as the first next-inspection item and `warning_boundaries` for the complete alphabetical list of report-only mechanics. `choose_one` is identity-gated direct; `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only. `generated_entity` and its `spell_generation` alias stay in partial visibility unless exact option or transformed-identity resolution exists.
- Reports to open for source-depth work: `per_card_config_readiness_report.json`, `guide_source_depth_report.json`, `claim_coverage_report.json`, `source_claim_gap_report.json`, `strong_promotion_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, and `global_values_authority_matrix.json`.
- Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link; `core_source_backed_fixture` rows are strict controls, `source_informed_valid_fixture` rows are valid with visible gaps, and operators should close existing matrix gaps before adding more representative decks. After durable Boarlock and Kingslayer preservation, there is no current actionable source-informed closure target.
- Keep exact CardID identity, full `GlobalValues` coverage, the profile report, the pre-run boundary, and no replay analysis.
- Do no replay analysis, winrate analysis, HSTuner follow-up, or after-game tuning.
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

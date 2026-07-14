---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name and deck code. Use when Codex must build or validate direct Mulligan, GlobalValues, `per-card <CARDID>.json`, or Combo runtime config before games are played.
---

# HSConfig

Use this skill when Codex must create or validate a pre-game HearthRanger VisionAI `CustomConfig` package from a deck name, deck code, and current guide-backed research. HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

For the normal operator entry point, start at `docs/operator/README.md`. Preferred normal path: `hsconfig configure`; Lower-level inspected path: source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply.
Inputs: deck name, deck code, runtime root for `prepare`, `build`, and `apply`, short source evidence rows from current guide research, optional researched `source_documents.json`, and normalized guide sources from `hsconfig research-deck`.

Normal workflow:

1. Prefer `hsconfig configure ...` for normal operation.
2. Use lower-level commands only when inspecting a stage:
   `source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply`.
3. Open `reports/operator_summary.json` first.

- Treat source claim kind and runtime surface authority as separate decisions.
  Generate the package for any valid deck, but only write a runtime row when
  the claim passes that surface's gate; otherwise keep the claim visible in
  reports.
- Use the canonical claim lifecycle for source-to-runtime explanations: source claim -> normalized `claim_kind` -> semantic qualifiers -> conflict quarantine -> surface gate -> builder/router outcome -> emitted runtime row or suppression reason. quarantined claims suppress unsafe runtime rows, stay visible in reports, and do not block load-safe valid packages. source_contract_audit.json is diagnostic; operator_summary.json remains the only normal apply authority.
- Source Contract Boundary: `claim_kind`, the source contract matrix, and the surface gate decide whether source evidence may lower to runtime config; effect relevance, guide importance, and archetype value do not bypass that chain. `operator_summary.json remains the normal apply authority`; source-contract reports are diagnostic only. Warnings are follow-up work, not runtime apply blockers. normal HSConfig output must not emit `Presume.json` or `Concede.json`.

Operator rules:

- Decode the deck code first, then resolve exact CardID identity before writing config.
- `hsconfig configure` is the normal one-command path; `source-manifest`, `draft-source-documents`, `hsconfig research-deck --source-documents-json`, and `hsconfig prepare --guide-sources-json` are inspected stages for fixtures, debugging, and research contract review.
- Use `reports/operator_summary.json` as the single operator gate. `VALID_PACKAGE` is runtime validity; `SOURCE_BACKED_STRONG`, `STATIC_SEMANTICS_USABLE`, and `VALID_BUT_NOT_GUIDE_STRONG` are confidence and source-depth labels.
- Runtime apply is guarded. Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`. Guarded apply validates `operator_summary.json`, package structure, fake receipts, and package hashes before writing.
- Read `runtime_load_safe`, `runtime_apply_mode`, `runtime_apply_allowed`, `runtime_apply_requires_flag`, and `apply_policy`. `ALLOWED_WITH_WARNINGS can still be runtime-write permission when technical_status=VALID_PACKAGE`; warnings describe source or semantic debt.
- Minimal `load_safe_apply` requires `GlobalValues.json` and `Mulligan.json`. `per-card <CARDID>.json` files and `Combo.json` are HSConfig rich-output repo policy, not the minimal runtime-write gate and not an official HearthRanger minimum.
- Open `operator_summary.json.mulligan_policy_status` for source-backed versus policy-backed Mulligan coverage. `operator_summary.json.default_only_runtime_surfaces` must normally be empty for generated deck packages; if it names a surface, inspect that surface report first.
- If no source-backed Mulligan keep can be emitted, allow `policy_backed_autonomous_mulligan` to emit a small low-curve keep set; it prevents default-only output, stays weaker than guide evidence, must not promote the deck to `SOURCE_BACKED_STRONG`, vetoes cards with explicit/suppressed/quarantined Mulligan source intent, and must not keep non-hand start-of-game enablers such as Darkbishop Benedictus without explicit opening-hand source text.
- Effect semantics are not opening-hand mulligan keeps. Preserve start-of-game, deckbuilding, and hero-power-transform behavior such as Darkbishop Benedictus -> Mind Spike, but do not place the enabler card in `Mulligan.json` unless a source explicitly describes opening-hand mulligan intent. Semantic qualifiers refine existing claims only: timing, zone, target, option, and state context support runtime decisions but never bypass `claim_kind` or matching surface gates, and never create another apply authority. operator_summary.json remains the normal apply authority.
- `globalvalue_numeric_tuning` is valid source evidence, but Step 1 treats it as runtime-evidence-required and report-visible. Use `gameplan_posture` for Step1 GlobalValues posture that may lower to `GlobalValues.json`.
- Source-contract invariant: effect semantics are preserved on supported effect/CardID surfaces, but only exact runtime-surface claims lower into matching runtime JSON. `source_contract_audit.json` is diagnostic; runtime-write authority stays in `operator_summary.json`.
- `source_contract_audit.json` explains why each claim did or did not lower.
- `contract_spine_rows` are diagnostic. They provide the compact source -> policy -> surface gate -> builder/router -> runtime effect chain for each claim kind. They do not grant apply permission, and operator_summary.json remains the normal apply authority.
- Developer diagnostic: `hsconfig contract-spine-sentinel --json` checks that claim-kind policy, conformance, diagnostic-only reports, and apply-boundary files still form one contract spine. It is not an operator gate; `operator_summary.json` remains the normal apply authority.
- Warnings are follow-up work, not a runtime apply blocker.
- Do not use `source_contract_audit.json` as an apply gate.
- When adding a claim kind, update all four boundaries together: `SUPPORTED_ATOMIC_CLAIM_KINDS`, `source_contract_matrix.py`, the matching surface gate, and a builder/router or diagnostic test; new claim kinds must not create another runtime-write gate, and `operator_summary.json` remains the only normal runtime-write/apply authority.
- If the VisionAI surface or identity is unresolved, keep the claim visible in reports and do not emit runtime JSON from it.
- The contract conformance snapshot is documentation-as-code for claim-kind policy, surface gates, and diagnostic impact. It does not create a second operator gate; operator_summary.json remains the normal apply authority.
- Treat unexpected contract drift as an implementation defect, but treat builder prerequisite gaps as visible no-block diagnostics. A builder prerequisite gap means the surface is allowed but the concrete claim is missing required structure, such as a complete combo sequence.
- Never treat `policy_lane` alone as runtime emission. Check `source_contract_audit.json.claim_lifecycle_rows` for source -> policy -> surface gate -> builder/router -> emitted/suppressed diagnostics, and use `operator_summary.json` for normal readiness.
- `reports/source_contract_audit.json` explains why each claim did or did not lower to `Mulligan.json`, `GlobalValues.json`, `Combo.json`, or `per-card <CARDID>.json`; it is diagnostic and does not replace `operator_summary.json`. Optional diagnostic: `hsconfig contract-doctor --package <package> --json`; operator_summary.json remains the only normal apply authority.
- `reports/source_to_runtime_explainability.json` is the card-readable diagnostic projection of the same chain. It names emitted runtime files, missing runtime files, first missing links, and next source actions per claim/card. `operator_summary.json.source_to_runtime_explainability_summary` is non-blocking and never grants apply permission.
- Open `operator_summary.json.source_claim_quality_summary` when a deck is valid but thin. It is non-blocking source-depth visibility, not a second apply path.
- When a package is technically valid but source depth is weak, continue and report the debt. Do not block valid deck packages because a claim is low confidence, report-only, unsupported by a runtime surface, or visible only in `source_contract_audit.json`.
- `Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.
- `load_safe_apply` is an HSConfig operator policy, not a HearthRanger public-doc term.
- Inspect `config_usefulness`, `load_safe_but_thin`, `usable_with_targeted_gaps`, `next_report_to_open`, `mechanic_visibility_summary`, `mechanic_drift_summary`, `reports/mechanic_drift_report.json`, `reports/semantic_enrichment_report.json`, and `no_block_failure_mode_summary` when a package has warnings. warning-only mechanics do not block load-safe apply, and this does not add another runtime-write gate.
- `technical_hard_block` stops apply. `source_depth_warning`, `warning_only_mechanic`, `future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and `runtime_evidence_only_tuning` are follow-up labels.
- The mechanic lowering registry is the executable authority behind `needs_mechanic_lowering`: `cards_needing_mechanic_lowering` only increments when a registered mechanic has a documented default CardID lowering target and no meaningful CardID row was emitted. Dredge, Tradeable, and unknown future mechanics stay report-only/warning-only and do not increment `cards_needing_mechanic_lowering`.
- Modern mechanic visibility is non-blocking. `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` should be named in reports when detected, but they must not block load-safe apply unless the package is technically invalid.
- `rewind`, `herald`, and `shatter` are warning-only report-only visibility labels. Name them in reports when detected; normal HSConfig does not map them to runtime surfaces, and they must not block load-safe apply.
- Use `first_warning_boundary` as the first next-inspection item and `warning_boundaries` for the complete alphabetical list of report-only mechanics. `choose_one` is identity-gated direct; `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only. `generated_entity` and its `spell_generation` alias stay in partial visibility unless exact option or transformed-identity resolution exists.
- Reports to open for source-depth work: `source_to_runtime_explainability.json`, `source_contract_audit.json`, `per_card_config_readiness_report.json`, `guide_source_depth_report.json`, `claim_coverage_report.json`, `source_claim_gap_report.json`, `strong_promotion_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, and `global_values_authority_matrix.json`.
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

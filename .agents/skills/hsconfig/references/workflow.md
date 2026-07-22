# Workflow

Preferred normal path: `hsconfig configure`; normal operator entry point: `docs/operator/README.md`.
Lower-level inspected path: source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply. Manual-only fallback uses source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply.

Normal workflow: prefer `hsconfig configure ...`; read `<out>/configure_summary.json.acceptance_summary` first after configure, then `configure_summary.json.handoff_contract` for compact diagnostic-only handoff proof; use lower-level commands only when inspecting a stage (`source-manifest -> source-autopilot or draft-source-documents -> research-deck -> prepare -> validate -> apply`); use `reports/operator_summary.json` as the apply authority.
Contract compiler checklist: `references/contract-compiler-checklist.md`.
Recommended fresh deck command: `hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --online-source --auto-source --apply --json`.

If public sources are thin, the command still writes a valid package and reports the first missing source action. Do not manually relabel `SOURCE_BACKED_PARTIAL` as `SOURCE_BACKED_STRONG`.
When compact public source-search records exist, `hsconfig configure --auto-source --source-search-results-json ...` writes `02_source_autopilot/source_documents.json` and feeds it into `hsconfig research-deck --source-documents-json` and `hsconfig prepare --guide-sources-json`. `source-autopilot` is source-strength preflight, not runtime apply authority; `decklist_only`, snippets, `policy_fallback`, `default_runtime`, and static records without explicit supported effect semantics do not promote `SOURCE_BACKED_STRONG`.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

Identity fields such as `hs_id` keep deck rows and examples unambiguous before games are played. hdt_deck_id is identity-only metadata, not replay evidence, not HDT parsing input, and not a post-run tuning source.

## Five-Step Sequence

1. Decode deck input and run `hsconfig source-manifest` when aliases, card targets, or research questions need inspection.
2. Collect guide, archetype, mulligan, card-text, and metadata evidence as short rows; run `hsconfig draft-source-documents` to create strict `source_documents.json`.
3. Run `hsconfig research-deck --source-documents-json ...` to write `deck_fingerprint.json`, `candidate_archetypes.json`, `guide_sources.json`, `guide_builder_receipt.json`, `source_evidence_verification_report.json`, and identity reports without runtime config.
4. Run `hsconfig prepare --guide-sources-json ...` to perform HearthSim deckstring decode, exact identity resolution, static semantic enrichment, research-contract compilation, `CustomConfig` output, and validation reports.
5. Read `reports/operator_summary.json` first, then run `hsconfig validate` or guarded `hsconfig apply` only when runtime writes are intended.

Normal `prepare` reports include `operator_summary.json`, `deckstring_decode_receipt.json`, `card_id_map.json`, `guide_builder_receipt.json`, `candidate_archetypes.json`, `identity_graph_report.json`, `guide_claim_bundle.json`, `claim_coverage_report.json`, `source_contract_audit.json`, `source_to_runtime_explainability.json`, `source_evidence_closure.json`, `source_claim_gap_report.json`, `strong_promotion_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, `global_values_authority_matrix.json`, `per_card_config_readiness_report.json`, `guide_source_depth_report.json`, `gameplan_contract.json`, `surface_intent.json`, validation reports, and `reports/research/*`.

`source_contract_audit.json.claim_lifecycle_rows` is diagnostic-only: it traces source -> policy -> surface gate -> builder/router -> emitted/suppressed. `policy_lane` is static policy, not runtime emission; readiness and apply authority stay in `operator_summary.json`. `hsconfig contract-doctor --package <package> --json` is optional runtime-read-only diagnostics; operator_summary.json remains the only normal apply authority.
`source_to_runtime_explainability.json` is the card-readable diagnostic projection of the same chain. It names emitted runtime files, missing runtime files, first missing links, and next source actions per claim/card. `operator_summary.json.source_to_runtime_explainability_summary` is non-blocking and never grants apply permission.
`source_evidence_closure.json` is the compact diagnostic package-quality closure summary; it mirrors source-to-runtime and operator summaries without creating another apply path.
`operator_summary.json.source_backed_strong_closure` and `operator_summary.json.no_default_only_runtime_status` are compact diagnostic-only summaries. `hsconfig source-closure-optimizer` is only a diagnostic closure view: it does not apply runtime files, does not promote candidate URLs to `SOURCE_BACKED_STRONG`, and does not replace `reports/operator_summary.json`; these views expose honest Strong closure and visible no-default-only runtime status without creating apply gates.
The contract conformance snapshot is documentation-as-code for claim-kind policy and surface-gate drift; it does not create a second operator apply path, and operator_summary.json remains the normal apply authority.

`contract_spine_rows` are diagnostic. They provide the compact source -> policy -> surface gate -> builder/router -> runtime effect chain for each claim kind. They do not grant apply permission, and operator_summary.json remains the normal apply authority.

Unexpected contract drift is a defect in the source-contract spine. A builder prerequisite gap is different: it means the surface is allowed, but the concrete claim still lacks required structure. Builder prerequisite gaps stay visible and support no-block package generation; they do not create a second operator apply path.

`Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.

## Gate And Readiness

After `configure`, `<out>/configure_summary.json.acceptance_summary` is the first-read operator projection: `use_config_now`, `technical_status`, `runtime_apply_allowed`, `source_strength`, `default_only_clean`, and `next_report_to_open` summarize the package. Read `<out>/configure_summary.json.handoff_contract` next as the pre-run config contract receipt: compact diagnostic-only handoff proof for use_config_now, single authority, no-default-only status, forbidden-surface status, source-to-runtime trace status, Darkbishop boundary, mechanic discipline, and the next report; it does not replace `reports/operator_summary.json`, cannot apply runtime files, cannot turn source gaps into blockers, and operator_summary.json remains the only normal apply authority. Then read `<out>/configure_summary.json.source_closure_receipt`, the compact diagnostic-only source-closure receipt for source-depth questions after `acceptance_summary` and `handoff_contract`: it shows canonical source status, no-default-only visibility, acquisition/source-document/claim counts, runtime-lowerable claim counts, and `first_missing_source_action`; does not replace `reports/operator_summary.json`; cannot promote, block, apply, or write runtime files; keeps source_status_apply_blocking=false; and means default-only runtime surfaces remain visible quality debt. `<out>/configure_summary.json.config_quality_summary` remains diagnostic-only and non-blocking, and `contract-doctor` provides details when attention is needed. `technical_status=VALID_PACKAGE` means HearthRanger JSON structure is valid. `SOURCE_BACKED_STRONG` means source depth supports a strong initial config. `STATIC_SEMANTICS_USABLE` means static semantics produced a safe baseline. `VALID_BUT_NOT_GUIDE_STRONG` means open `guide_strength_summary` and `semantic_blockers`.

`config_intent_self_audit` is part of the config-quality diagnostic path and verifies runtime-file intent without creating a gameplay sequencing engine or a second runtime apply authority.

`runtime_apply_mode` is the human-readable write mode. `hsconfig apply` and `apply_package()` still re-evaluate the operator gate before writing. `technical_status=VALID_PACKAGE` plus `runtime_load_safe=true` and `runtime_apply_mode=load_safe_apply` is the normal initial write boundary. `SOURCE_BACKED_STRONG` is the confidence label, not the runtime-write gate.

Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.

Minimal load-safe runtime apply requires `GlobalValues.json` and `Mulligan.json`. `per-card <CARDID>.json` files, `Combo.json`, and source-backed choice lowering make the package richer, but they are HSConfig rich-output repo policy rather than the minimal runtime-write gate.
`config_usefulness`, `load_safe_but_thin`, `usable_with_targeted_gaps`, `source_contract_audit_summary`, `source_to_runtime_explainability_summary`, `source_evidence_closure_summary`, `no_block_failure_mode_summary`, `mechanic_visibility_summary`, `mechanic_drift_summary`, `reports/source_contract_audit.json`, `reports/source_to_runtime_explainability.json`, `reports/source_evidence_closure.json`, `reports/mechanic_drift_report.json`, and `reports/semantic_enrichment_report.json` explain source, mechanic, and richness gaps. `technical_hard_block` stops apply; warning categories such as `source_depth_warning`, `warning_only_mechanic`, `future_mechanic_drift`, `guide_strength_gap`, `combo_uncertainty`, and `runtime_evidence_only_tuning` do not create a second apply path. This does not create a second apply path when `technical_status=VALID_PACKAGE`.

Effect semantics are preserved on supported effect/CardID surfaces, but only exact runtime-surface claims lower into matching runtime JSON; `source_contract_audit.json` is diagnostic and `operator_summary.json` remains the normal apply authority. Semantic qualifiers refine existing claims with timing, zone, target, option, or state context. They do not bypass `claim_kind` or surface gates, and they do not create a second apply path. An effect without explicit opening-hand or mulligan wording remains effect semantics, not a `Mulligan.json` keep.
Card-intent taxonomy is diagnostic-only; it explains per-card config signals but does not encode HearthRanger gameplay sequencing or create another apply gate.

`operator_summary.json` remains the only normal apply authority.
`source_contract_audit.json` explains why each claim did or did not lower.
`contract_spine_rows` show the compact source -> policy -> surface gate -> builder/router -> runtime effect chain.
Warnings are follow-up work, not a runtime apply blocker.
Do not use `source_contract_audit.json` as an apply gate.

## Mechanic Visibility

The mechanic lowering registry is the executable authority behind `needs_mechanic_lowering`. `cards_needing_mechanic_lowering` only increments when a registered mechanic has a documented default CardID lowering target and no meaningful CardID row was emitted. Dredge, Tradeable, and unknown future mechanics stay report-only/warning-only and do not increment `cards_needing_mechanic_lowering`.

Modern mechanic visibility is non-blocking. `kindred`, `tourist`, `starship`, `spellburst`, `miniaturize`, `quickdraw`, `honorable_kill`, `elusive`, `poisonous`, and `imbue` surface as partial or warning-only visibility labels, not runtime write blockers. Unknown mechanics are warning-only and do not block load-safe apply.

`rewind`, `herald`, and `shatter` are warning-only report-only visibility labels. HSConfig names them in reports and does not map them to runtime surfaces.

Use `first_warning_boundary` as the first next-inspection item and `warning_boundaries` as the complete alphabetical list of report-only mechanics. `choose_one` is identity-gated direct; `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool` are warning-only. `generated_entity` and its `spell_generation` alias stay in `partial` visibility unless exact option or transformed-identity resolution exists.

## Source-Depth And Diagnostics

Every card should land in a visible source-depth lane before preparation: guide-backed claim, source-backed static semantics, archetype-inferred role, explicit low confidence, generic low confidence, or contract gap. When a guide-backed card surface is documented, the runtime file family is `per-card <CARDID>.json`.

Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link, and operators should close existing matrix gaps before adding more representative decks. `core_source_backed_fixture` rows are strict controls; `source_informed_valid_fixture` rows are valid packages with visible gaps. After durable Boarlock and Kingslayer preservation, the current actionable source-informed closure targets are CtAPaladin, Discolock, TreantDruid, and PirateDH. `contract-preflight.research_context.latest_research_result_contract_first_non_promoting_*` names the first source action needed for Strong closure; it is diagnostic-only, cannot block or promote a package, and operator_summary.json remains the only normal apply authority.

Use `hsconfig research-contract` only when the research bundle should be inspected before compiling config files. Use `hsconfig build` as a lower-level command when a caller already controls explicit `--cards-json`, legacy `--claims-json`, structured `--guide-sources-json`, or inspected `--plan-reports-dir` inputs. Use `--allow-placeholder` only for deterministic fixture or preview tests.

Guarded apply copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder. Use fake apply for receipt-bound previews before any requested runtime write.

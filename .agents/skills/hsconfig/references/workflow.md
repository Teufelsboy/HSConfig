# Workflow

Normal flow: deck input -> guide research -> researched source documents for
every deck card in `source_documents.json` ->
`hsconfig research-deck --source-documents-json ...` ->
normalized guide sources ->
`hsconfig prepare --guide-sources-json ...` ->
HearthSim deckstring decode -> exact identity -> card metadata ->
guide/static research contract -> guide-backed gameplan -> plan reports ->
operator summary -> readiness/depth reports -> compilers -> validation ->
optional runtime apply.

HSConfig has two useful success levels.

VALID_PACKAGE means the runtime JSON package is structurally valid and load-safe.
SOURCE_BACKED_STRONG means the package has current guide-backed per-card coverage and can be treated as a strong initial config.

STATIC_SEMANTICS_USABLE and VALID_BUT_NOT_GUIDE_STRONG are safe handoff states, not optimized-config claims.

Readiness interpretation:

1. `technical_status=VALID_PACKAGE` means HearthRanger JSON structure is valid.
2. `semantic_status=SOURCE_BACKED_STRONG` means the card-level source coverage is strong enough for a high-confidence initial config.
3. If `semantic_status=VALID_BUT_NOT_GUIDE_STRONG`, open `semantic_blockers` first. Each blocker has `reason`, `count`, `blocking_strength`, `report`, and top affected cards.
4. Improve `source_documents.json` for `cards_need_guide_claims`; improve claim lowering or keep report-only for `cards_need_runtime_surface`; add exact sequence data for `cards_need_combo_sequence`.

Use `hsconfig research-deck --source-documents-json ...` to normalize source
documents before compilation.
It writes `deck_fingerprint.json`, `candidate_archetypes.json`,
`guide_sources.json`, `guide_builder_receipt.json`, and identity reports, but no
runtime package.

Use `hsconfig prepare` for package creation. It writes `operator_summary.json`, `deckstring_decode_receipt.json`, `card_id_map.json`, `guide_builder_receipt.json`, `candidate_archetypes.json`, `identity_graph_report.json`, `guide_claim_bundle.json`, `claim_coverage_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, `global_values_authority_matrix.json`, `per_card_config_readiness_report.json`, `guide_source_depth_report.json`, `gameplan_contract.json`, `surface_intent.json`, validation reports, and `reports/research/*`.

Use `hsconfig research-contract` only when the research bundle should be inspected before compiling config files. It writes no `CustomConfig` runtime package.

Use `hsconfig build` as a lower-level command when a caller already controls explicit `--cards-json`, legacy `--claims-json`, structured `--guide-sources-json`, or inspected `--plan-reports-dir` inputs. It still writes `reports/research/*`. Use `--allow-placeholder` only for deterministic fixture or preview tests.

Use `hsconfig validate` before handoff or apply. Use `operator_summary.json` for next action and semantic depth. Use `hsconfig apply` only when requested by the user or task; apply copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder.

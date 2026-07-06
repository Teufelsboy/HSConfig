# Workflow

Normal flow: deck input -> guide research -> researched source documents for
every deck card -> `hsconfig research-deck` -> normalized guide sources ->
`hsconfig prepare --guide-sources-json ...` ->
HearthSim deckstring decode -> exact identity -> card metadata ->
guide/static research contract -> guide-backed gameplan -> plan reports ->
operator summary -> readiness/depth reports -> compilers -> validation ->
optional runtime apply.

Use `hsconfig research-deck` to normalize source documents before compilation.
It writes `deck_fingerprint.json`, `candidate_archetypes.json`,
`guide_sources.json`, `guide_builder_receipt.json`, and identity reports, but no
runtime package.

Use `hsconfig prepare` for package creation. It writes `operator_summary.json`, `deckstring_decode_receipt.json`, `card_id_map.json`, `guide_builder_receipt.json`, `candidate_archetypes.json`, `identity_graph_report.json`, `guide_claim_bundle.json`, `claim_coverage_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, `global_values_authority_matrix.json`, `per_card_config_readiness_report.json`, `guide_source_depth_report.json`, `gameplan_contract.json`, `surface_intent.json`, validation reports, and `reports/research/*`.

Use `hsconfig research-contract` only when the research bundle should be inspected before compiling config files. It writes no `CustomConfig` runtime package.

Use `hsconfig build` as a lower-level command when a caller already controls explicit `--cards-json`, legacy `--claims-json`, structured `--guide-sources-json`, or inspected `--plan-reports-dir` inputs. It still writes `reports/research/*`. Use `--allow-placeholder` only for deterministic fixture or preview tests.

Use `hsconfig validate` before handoff or apply. Use `operator_summary.json` for next action and semantic depth. Use `hsconfig apply` when the user explicitly asks or has requested autonomous runtime apply; apply copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder.

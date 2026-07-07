# Workflow

Normal flow: deck input -> guide research -> `source_documents.json` -> `hsconfig research-deck --source-documents-json ...` -> normalized guide sources -> `hsconfig prepare --guide-sources-json ...` -> `reports/operator_summary.json` -> validation -> `hsconfig apply ...` only when requested.

## Research Normalization

Use `hsconfig research-deck --source-documents-json ...` after Codex has collected guide, archetype, mulligan, card-text, and metadata evidence. It writes `deck_fingerprint.json`, `candidate_archetypes.json`, `guide_sources.json`, `guide_builder_receipt.json`, and identity reports, but no runtime package.

Every card should land in a visible source-depth lane before preparation: guide-backed claim, source-backed static semantics, archetype-inferred role, explicit low confidence, generic low confidence, or contract gap.

## Package Preparation

Use `hsconfig prepare --guide-sources-json ...` for normal package creation. It performs HearthSim deckstring decode, resolves exact identity, enriches card metadata, builds the guide/static research contract, compiles runtime config, validates JSON, and writes the operator reports.

Important outputs include `operator_summary.json`, `deckstring_decode_receipt.json`, `card_id_map.json`, `guide_builder_receipt.json`, `candidate_archetypes.json`, `identity_graph_report.json`, `guide_claim_bundle.json`, `claim_coverage_report.json`, `source_claim_gap_report.json`, `strong_promotion_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, `global_values_authority_matrix.json`, `per_card_config_readiness_report.json`, `guide_source_depth_report.json`, `gameplan_contract.json`, `surface_intent.json`, validation reports, and `reports/research/*`.

For source-informed packages, open `source_claim_gap_report.json` first to see the card-level missing link, then open `strong_promotion_report.json` for the promotion verdict.

## Readiness Interpretation

Read `reports/operator_summary.json` before handoff or runtime apply.
`reports/operator_summary.json` is the single operator gate for normal handoff or apply decisions. Lower-level reports explain why the package is strong, warning-only, or still needs source work.

1. `technical_status=VALID_PACKAGE` means HearthRanger JSON structure is valid.
2. `semantic_status=SOURCE_BACKED_STRONG` means the card-level source coverage supports a strong initial config.
3. `semantic_status=STATIC_SEMANTICS_USABLE` means static semantics produced a safe baseline, not guide-depth confidence.
4. `semantic_status=VALID_BUT_NOT_GUIDE_STRONG` means the package is valid but the operator should open `guide_strength_summary` and `semantic_blockers`.

For blockers, improve `source_documents.json` for `cards_need_guide_claims`; improve claim lowering or keep report-only for `cards_need_runtime_surface`; add exact sequence data for `cards_need_combo_sequence`; resolve source conflicts before calling the package source-backed strong.

## Fixture Stage Semantics

`core_source_backed_fixture` means the fixture produces `SOURCE_BACKED_STRONG` and can be used as a strict control example. `source_informed_valid_fixture` means it produces a valid package but still has source-depth or lowering gaps. Treat `operator_summary.json` as the single operator gate for both stages. Do not claim a source-informed fixture is optimized or strong until its blockers are closed.

## Diagnostic And Expert Paths

Use `hsconfig research-contract` only when the research bundle should be inspected before compiling config files. It writes no `CustomConfig` runtime package.

Use `hsconfig build` as a lower-level command when a caller already controls explicit `--cards-json`, legacy `--claims-json`, structured `--guide-sources-json`, or inspected `--plan-reports-dir` inputs. It still writes `reports/research/*`. Use `--allow-placeholder` only for deterministic fixture or preview tests.

Use `hsconfig validate` before handoff or apply. Use `hsconfig apply` only when requested by the user or task; apply copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder.

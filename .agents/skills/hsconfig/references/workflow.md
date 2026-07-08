# Workflow

Normal flow: deck input -> `hsconfig source-manifest` -> short evidence rows -> `hsconfig draft-source-documents` -> `source_documents.json` -> `hsconfig research-deck --source-documents-json ...` -> normalized guide sources -> `hsconfig prepare --guide-sources-json ...` -> `reports/operator_summary.json` -> validation -> `hsconfig apply ...` only when requested.

For the normal operator entry point, start at `docs/operator/README.md`.

HSConfig is pre-run only. It does not parse replays, inspect winrate, analyze runtime logs, promote candidates, or tune after games. Those tasks belong to HSTuner.

Identity fields such as `hs_id` keep deck rows and examples unambiguous before games are played. hdt_deck_id is identity-only metadata, not replay evidence, not HDT parsing input, and not a post-run tuning source.

## Research Normalization

Use `hsconfig source-manifest` first to get aliases, card targets, and research questions. Codex then writes short evidence rows. Use `hsconfig draft-source-documents` to turn those rows into strict `source_documents.json`.

Use `hsconfig research-deck --source-documents-json ...` after Codex has collected guide, archetype, mulligan, card-text, and metadata evidence. It writes `deck_fingerprint.json`, `candidate_archetypes.json`, `guide_sources.json`, `guide_builder_receipt.json`, `source_evidence_verification_report.json`, and identity reports, but no runtime package.

Every card should land in a visible source-depth lane before preparation: guide-backed claim, source-backed static semantics, archetype-inferred role, explicit low confidence, generic low confidence, or contract gap.
When a guide-backed card surface is documented, the runtime file family is `per-card <CARDID>.json`.

## Package Preparation

Use `hsconfig prepare --guide-sources-json ...` for normal package creation. It performs HearthSim deckstring decode, resolves exact identity, enriches card metadata, builds the guide/static research contract, compiles runtime config, validates JSON, and writes the operator reports.

Important outputs include `operator_summary.json`, `deckstring_decode_receipt.json`, `card_id_map.json`, `guide_builder_receipt.json`, `candidate_archetypes.json`, `identity_graph_report.json`, `guide_claim_bundle.json`, `claim_coverage_report.json`, `source_claim_gap_report.json`, `strong_promotion_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, `global_values_authority_matrix.json`, `per_card_config_readiness_report.json`, `guide_source_depth_report.json`, `gameplan_contract.json`, `surface_intent.json`, validation reports, and `reports/research/*`.

For source-informed packages, open `source_claim_gap_report.json` first to see the card-level missing link, then open `strong_promotion_report.json` for the promotion verdict.
`source_depth_lane` is the readable alias for the first missing source-to-runtime link in those source-informed reports. It does not grant apply permission; `reports/operator_summary.json` remains the single operator gate.

## Readiness Interpretation

Read `reports/operator_summary.json` before handoff or runtime apply.
`reports/operator_summary.json` is the single operator gate for normal handoff or apply decisions. Lower-level reports explain why the package is strong, warning-only, or still needs source work.

1. `technical_status=VALID_PACKAGE` means HearthRanger JSON structure is valid.
2. `semantic_status=SOURCE_BACKED_STRONG` means the card-level source coverage supports a strong initial config.
3. `semantic_status=STATIC_SEMANTICS_USABLE` means static semantics produced a safe baseline, not guide-depth confidence.
4. `semantic_status=VALID_BUT_NOT_GUIDE_STRONG` means the package is valid but the operator should open `guide_strength_summary` and `semantic_blockers`.
5. `runtime_apply_mode` is the human-readable write mode. It is descriptive; `hsconfig apply` and `apply_package()` still re-evaluate the operator gate before writing.

For blockers, improve `source_documents.json` for `cards_need_guide_claims`; improve claim lowering or keep report-only for `cards_need_runtime_surface`; add exact sequence data for `cards_need_combo_sequence`; resolve source conflicts before calling the package source-backed strong.

`SOURCE_INFORMED_APPLY_READY` with `ALLOWED_SOURCE_INFORMED` and `source_informed_apply_readiness.status=ready` is the only valid source-informed apply lane. It allows `hsconfig apply --package <package> --runtime-root <runtime-root> --allow-source-informed --json` when the remaining blockers are only `cards_need_guide_claims` or `cards_need_mulligan_claims`. `cards_need_runtime_surface` and other hard blockers keep the lane blocked. Source-informed apply is still not `SOURCE_BACKED_STRONG`; use `source_claim_gap_report.json` and `strong_promotion_report.json` to close those links before promotion.

Source-informed apply remains pre-run only. It is not replay analysis, winrate validation, HSTuner candidate promotion, or post-run tuning.

Guarded apply is still pre-run. It protects the write step with fake receipts, package hashes, snapshots, rollback evidence, and write history; it does not inspect games or tune from logs.
Use fake apply for receipt-bound previews before any requested runtime write.

## Fixture Stage Semantics

`core_source_backed_fixture` means the fixture produces `SOURCE_BACKED_STRONG` and can be used as a strict control example. `source_informed_valid_fixture` means it produces a valid package but still has source-depth or lowering gaps. Treat `operator_summary.json` as the single operator gate for both stages. Do not claim a source-informed fixture is optimized or strong until its blockers are closed.
Source-depth closure means every representative deck either proves `SOURCE_BACKED_STRONG` or exposes the first missing source-to-runtime link, and operators should close existing matrix gaps before adding more representative decks.
Current closure order is Boarlock first, Kingslayer second. Boarlock stays first because it is the only representative `Combo.json` control row. Kingslayer follows because its remaining gap is narrower and tied to `DEEP_014` / `Quick Pick`.

## Diagnostic And Expert Paths

Use `hsconfig research-contract` only when the research bundle should be inspected before compiling config files. It writes no `CustomConfig` runtime package.

Use `hsconfig build` as a lower-level command when a caller already controls explicit `--cards-json`, legacy `--claims-json`, structured `--guide-sources-json`, or inspected `--plan-reports-dir` inputs. It still writes `reports/research/*`. Use `--allow-placeholder` only for deterministic fixture or preview tests.

When apply is allowed, it copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder.
Use `hsconfig validate` before handoff or apply. Use `hsconfig apply` only when runtime writes are intended; it enforces `reports/operator_summary.json` and blocks by default unless the package is source-backed ready. Use `--allow-source-informed` only for `SOURCE_INFORMED_APPLY_READY` packages.

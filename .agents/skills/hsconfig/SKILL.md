---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name and deck code. Use when Codex must build or validate direct Mulligan, GlobalValues, per-card CardID, or Combo runtime config before games are played.
---

# HSConfig

Use this skill to build direct guide-aligned HearthRanger VisionAI `CustomConfig` packages.

Inputs:

- deck name
- deck code
- optional expert card JSON override
- optional legacy source-backed guide claims JSON list
- optional researched source documents JSON
- optional normalized guide sources JSON from `hsconfig research-deck`
- runtime root for `prepare` / `build` baseline profiling and for `apply`

Workflow:

1. Decode the deck code first, then resolve deck identity and card metadata.
2. Research current guide/archetype/card-usage sources.
3. Write researched source documents with card-specific claims.
4. Run `hsconfig research-deck --source-documents-json ...` when source documents exist, or run it without sources to create static-semantics fallback artifacts.
5. Check that the normalized guide sources give every deck card a card role,
   mulligan stance, usage expectation, mechanic expectation, combo relation, or
   explicit low-confidence fallback.
6. Run `hsconfig prepare --guide-sources-json ...`.
7. Verify `operator_summary.json`, the research contract, and
   `claim_coverage_report.json`,
   `mulligan_plan_report.json`, `card_behavior_plan_report.json`,
   `combo_plan_report.json`, `global_values_authority_matrix.json`,
   `per_card_config_readiness_report.json`, and
   `guide_source_depth_report.json`.
8. Apply when `operator_summary.json` has `technical_status=VALID_PACKAGE`,
   the user requested autonomous runtime apply, and the `next_action` does not
   ask for more source work before strong apply.

Rules:

- Build direct guide-aligned configs only.
- Use `--cards-json` only as an expert override, and `--allow-placeholder` only for fixture/test previews.
- Prefer `--guide-sources-json` over legacy `--claims-json` when live guide research was performed.
- Use `operator_summary.json` as the operator-facing readiness file; do not confuse `semantic_status` with runtime validity.
- VALID_PACKAGE means the JSON package loads structurally.
- SOURCE_BACKED_STRONG means HSConfig has enough current guide-backed coverage for strong initial config.
- STATIC_SEMANTICS_USABLE means the package is safe but not guide-depth.
- VALID_BUT_NOT_GUIDE_STRONG means Codex should improve source documents before calling the package optimized.
- Keep full `GlobalValues` coverage and write the profile report.
- Do no replay analysis, winrate analysis, postgame tuning, HSTuner candidate promotion, or runtime log parsing.
- Runtime apply is allowed after validation when the user asked for autonomous apply.
- Do not emit `Presume.json` or `Concede.json` in the normal path; they are legacy/gated surfaces only.
- Tell the user whether the package is guide-backed, static-semantics-backed, or still needs more research.

References:

- `references/workflow.md`
- `references/visionai-surfaces.md`
- `references/guide-research-policy.md`
- `references/globalvalues-policy.md`
- `references/card-behavior-policy.md`

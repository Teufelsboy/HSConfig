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
- optional structured guide sources JSON from current guide/archetype research
- runtime root for `prepare` / `build` baseline profiling and for `apply`

Workflow:

1. Decode the deck code first, then resolve deck identity and card metadata.
2. Research current guide/archetype/card-usage sources.
3. Write structured guide sources with card-specific claims.
4. Run `hsconfig prepare --guide-sources-json ...`.
5. Verify the research contract plus `claim_coverage_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, and `global_values_authority_matrix.json`.
6. Apply only after validation is green.

Rules:

- Build direct guide-aligned configs only.
- Use `--cards-json` only as an expert override, and `--allow-placeholder` only for fixture/test previews.
- Prefer `--guide-sources-json` over legacy `--claims-json` when live guide research was performed.
- Keep full `GlobalValues` coverage and write the profile report.
- Do no replay analysis, winrate analysis, postgame tuning, HSTuner candidate promotion, or runtime log parsing.
- Runtime apply only when the user asks.
- Do not emit `Presume.json` or `Concede.json` in the normal path; they are legacy/gated surfaces only.
- Tell the user whether the package is guide-backed, static-semantics-backed, or still has uncovered cards.

References:

- `references/workflow.md`
- `references/visionai-surfaces.md`
- `references/guide-research-policy.md`
- `references/globalvalues-policy.md`
- `references/card-behavior-policy.md`

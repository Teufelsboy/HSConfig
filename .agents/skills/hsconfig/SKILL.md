---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name and deck code. Use when Codex must build or validate direct Mulligan, GlobalValues, per-card CardID, or Combo runtime config before games are played.
---

# HSConfig

Use this skill when Codex must create or validate a pre-game HearthRanger VisionAI `CustomConfig` package from a deck name, deck code, and current guide-backed research. Keep HSConfig lean and separate from HSTuner.

Inputs:

- deck name
- deck code
- runtime root for `prepare`, `build`, and `apply`
- researched `source_documents.json`
- normalized guide sources from `hsconfig research-deck`
- optional expert `--cards-json`, legacy `--claims-json`, or inspected `--plan-reports-dir`

Normal workflow:

1. Decode the deck code first, then resolve deck identity and card metadata.
2. Research current guide, archetype, mulligan, and card-usage sources.
3. Write `source_documents.json` with card-specific claims.
4. Run `hsconfig research-deck --source-documents-json ...` to create normalized guide sources and the research contract inputs.
5. Run `hsconfig prepare --guide-sources-json ...` to compile the package and reports.
6. Read `reports/operator_summary.json` first, then inspect the research contract, `claim_coverage_report.json`, `mulligan_plan_report.json`, `card_behavior_plan_report.json`, `combo_plan_report.json`, `global_values_authority_matrix.json`, `per_card_config_readiness_report.json`, and `guide_source_depth_report.json`.
7. Run `hsconfig apply ...` only when requested; runtime apply is allowed after validation only when `technical_status=VALID_PACKAGE`, the user requested runtime writes, and `next_action` / `apply_policy` do not ask for more source work before apply.
8. Use `reports/operator_summary.json` as the single operator gate. Detail reports are evidence, not independent apply permissions.

Status meaning:

- `VALID_PACKAGE`: runtime JSON is structurally valid and load-safe.
- `SOURCE_BACKED_STRONG`: current guide-backed per-card coverage supports a strong initial config.
- `STATIC_SEMANTICS_USABLE`: static card semantics produced a valid package without enough live guide depth.
- `VALID_BUT_NOT_GUIDE_STRONG`: the package is valid, but `guide_strength_summary` and `semantic_blockers` identify missing source depth, conflict resolution, runtime-surface gaps, or combo detail.

Rules:

- Build direct guide-aligned configs only.
- Prefer `--guide-sources-json` over legacy `--claims-json` when live guide research was performed.
- Use `--cards-json` only as an expert override, and `--allow-placeholder` only for fixture/test previews.
- Use `operator_summary.json` as the operator-facing readiness file and single operator gate; do not confuse `semantic_status` with runtime validity.
- Keep exact CardID identity, full `GlobalValues` coverage, and the profile report.
- Do no replay analysis, winrate analysis, postgame tuning, HSTuner candidate promotion, or runtime log parsing.
- Do not emit `Presume.json` or `Concede.json` in the normal path; they are legacy/gated surfaces only.
- Tell the user whether the package is guide-backed, static-semantics-backed, or still needs more research.

References:

- `references/workflow.md`
- `references/visionai-surfaces.md`
- `references/guide-research-policy.md`
- `references/globalvalues-policy.md`
- `references/card-behavior-policy.md`

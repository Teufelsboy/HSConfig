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
- optional source-backed guide claims JSON list
- runtime root for `prepare` / `build` baseline profiling and for `apply`

Workflow:

1. Use `hsconfig prepare` as the normal deck-to-config path.
2. Decode the deck code first and record exact CardIDs in `deckstring_decode_receipt.json` and `card_id_map.json`.
3. Write the research contract under `reports/research/`: archetype, claims, card roles, mulligan anchors, usage expectations, bad patterns, and GlobalValues intent.
4. Generate direct runtime config surfaces only: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` when a concrete valid combo exists.
5. Validate the package before any apply.
6. Runtime apply only when the user asks; apply updates `CustomConfig/deck_config.ini` for the visible HearthRanger deck name.

Rules:

- Build direct guide-aligned configs only.
- Use `--cards-json` only as an expert override, and `--allow-placeholder` only for fixture/test previews.
- Keep full `GlobalValues` coverage and write the profile report.
- Do no replay analysis, winrate analysis, postgame tuning, HSTuner candidate promotion, or runtime log parsing.
- Do not emit `Presume.json` or `Concede.json` in the normal path; they are legacy/gated surfaces only.

References:

- `references/workflow.md`
- `references/visionai-surfaces.md`
- `references/guide-research-policy.md`
- `references/globalvalues-policy.md`
- `references/card-behavior-policy.md`

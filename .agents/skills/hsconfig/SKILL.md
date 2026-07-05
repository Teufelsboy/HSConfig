---
name: hsconfig
description: Generate guide-aligned HearthRanger VisionAI CustomConfig packages from a Hearthstone deck name, deck code, and optional card list. Use when Codex must build or validate direct Mulligan, GlobalValues, per-card CardID, or Combo runtime config before games are played.
---

# HSConfig

Use this skill to build direct guide-aligned HearthRanger VisionAI `CustomConfig` packages.

Inputs:

- deck name
- deck code
- optional card JSON list
- optional source-backed guide claims JSON list
- runtime root only when applying

Workflow:

1. Build or inspect deck identity and exact CardIDs.
2. Generate direct runtime config surfaces only: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` when a concrete valid combo exists.
3. Validate the package before any apply.
4. Runtime apply only when the user asks.

Rules:

- Build direct guide-aligned configs only.
- Keep full `GlobalValues` coverage and write the profile report.
- Do no replay analysis, winrate analysis, postgame tuning, HSTuner candidate promotion, or runtime log parsing.
- Do not emit `Presume.json` or `Concede.json` unless an explicit enabled policy exists.

References:

- `references/workflow.md`
- `references/visionai-surfaces.md`
- `references/guide-research-policy.md`
- `references/globalvalues-policy.md`
- `references/card-behavior-policy.md`

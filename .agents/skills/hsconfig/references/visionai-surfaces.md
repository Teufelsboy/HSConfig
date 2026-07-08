# VisionAI Surfaces

Supported runtime files:

- `GlobalValues.json`
- `Mulligan.json`
- `per-card <CARDID>.json`
- `Combo.json` when a concrete valid combo exists

Normal HSConfig output is limited to the files above. `Presume.json` and `Concede.json` remain legacy/gated validator-supported surfaces and are not part of the normal path package output or operator handoff.

Choice-surface lowering for `discover_choice` and `choose_one_choice` stays within `per-card <CARDID>.json` and only lowers when option identity is source-backed; unresolved identities remain report-visible.

Reports stay under `reports/` and must not be copied into runtime deck folders.

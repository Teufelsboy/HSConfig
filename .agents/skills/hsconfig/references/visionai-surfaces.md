# VisionAI Surfaces

Supported runtime files:

- `GlobalValues.json`
- `Mulligan.json`
- `per-card <CARDID>.json`
- `Combo.json` when a concrete valid combo exists

Normal HSConfig output is limited to the files above. `Concede.json` is publicly documented; `Presume.json` is legacy/public compatibility without a current verified first-party help-page citation, and normal HSConfig does not emit `Presume.json` or `Concede.json`; absence never blocks a valid load-safe package.

Choice-surface lowering for `discover_choice` and `choose_one_choice` stays within `per-card <CARDID>.json` and only lowers when option identity is source-backed; unresolved identities remain report-visible.

Reports stay under `reports/` and must not be copied into runtime deck folders.

# VisionAI Surfaces

Supported runtime files:

- `GlobalValues.json`
- `Mulligan.json`
- `per-card <CARDID>.json`
- `Combo.json` when a concrete valid combo exists

Normal HSConfig output is limited to the files above. `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.

Open `reports/operator_summary.json` first. Other reports explain source quality, mechanic coverage, ownership, and missing links. They do not grant apply permission.

Choice-surface lowering for `discover_choice` and `choose_one_choice` stays within `per-card <CARDID>.json` and only lowers when option identity is source-backed; unresolved identities remain report-visible.

Reports stay under `reports/` and must not be copied into runtime deck folders.

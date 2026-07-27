# VisionAI Surfaces

Supported runtime files:

- `GlobalValues.json`
- `Mulligan.json`
- `per-card <CARDID>.json`
- `Combo.json` when a concrete valid combo exists

Normal HSConfig output is limited to the files above. `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.

Open `reports/operator_summary.json` first. Other reports explain source quality, mechanic coverage, ownership, and missing links. They do not grant apply permission.

Choice-surface lowering for `discover_choice` and `choose_one_choice` stays within `per-card <CARDID>.json` and only lowers when option identity is source-backed; unresolved identities remain report-visible.

Linked runtime entities may own physical CardID files. Source card: `SW_448` (Darkbishop Benedictus); link: `hero_power_transform`; runtime owner: `EX1_625t` (Mind Spike); physical row: `CardID/EX1_625t.json`. The numeric bonus is configuration policy, not proof of optimal play.

The audited twelve-deck read-only acceptance additionally requires:

- semantic-enrichment type and linked-owner proof that no spell source or
  physical runtime owner has `OnBoardBonus` or `BeforeBattlecryTargetBonus`;
- typed, duplicate-preserving physical/report parity in both directions before
  source-claim/source-ref provenance is checked for every meaningful row;
- no unconditional lowering of a suppressed unsupported condition;
- no static Boarlock `Combo.json`, no coverage-only Discolock
  `InHandPlayPriority`, and exact ImbueMage Mulligan/readiness identity parity.

It prepares only temporary packages under a network-deny sentinel, stubs the
runtime writer entry, keeps the runtime root absent, and requires no apply
receipt. It does not prove in-client execution or gameplay optimality. Fixture
manifests do not authorize apply; `reports/operator_summary.json` remains the
sole current package authority.

Reports stay under `reports/` and must not be copied into runtime deck folders.

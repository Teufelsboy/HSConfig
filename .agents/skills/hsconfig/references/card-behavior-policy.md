# Card Behavior Policy

Every deck card must be represented in the gameplan contract.

Emit `<CARDID>.json` when documented VisionAI syntax can express a guide-backed
behavior, priority, target, discover, choice, attack, hero-power, overkill,
end-turn, upgrade, or timing rule.

Prefer the most specific documented block:

- `InHandBonus` for card value while held.
- `OnBoardBonus` for board-presence value.
- `BeforePlayCardBonus` for play-now timing.
- `BeforeBattlecryTargetBonus` for targeted Battlecry behavior.
- `BeforeUseHeroPowerBonus` for active hero-power use.
- `BeforePhysicalAttackBonus` for minion, hero, or weapon attack posture.
- `BeforeOverkilledBonus` for Overkill-specific payoff lines.
- `BeforeEndTurnBonus` for end-turn state preferences.
- `OnDiscoverCardBonus` for Discover option preferences.
- `OnChooseOneCardBonus` for resolved Choose One option preferences.
- `OnAdaptCardBonus` for resolved Adapt option preferences.
- `BeforeUpgradeCardBonus` for documented upgrade behavior.
- `InHandPlayPriority` and `OnBoardPlayPriority` only for search-order hints.

Guide claims may request a specific `runtime_block` only when the block is part
of the documented CardID behavior registry. Unsupported blocks stay in reports.

CardID behavior block support is source-backed and block-specific:

- `targeting_rule` claims may lower to target, play, attack, overkill, Discover, Choose One, or Hero Power blocks when the source names a matching behavior.
- `mechanic_usage` and `card_role` claims may create runtime rows only when static card text or guide text gives a clear behavior.
- `known_bad_pattern` claims stay report-only unless they map to a documented negative value row.
- `tech_slot` and `replacement_option` claims are operator context and do not become CardID runtime rows by default.

`meaningful_runtime_surface=true` means the row expresses specific guide-backed
runtime behavior. Generic generated CardID fallback files stay visible, but they
do not prove deep card-specific lowering.

If a claim cannot be lowered safely, keep it in
`card_behavior_suppression_report.json` instead of inventing unsupported runtime
syntax.

Do not emit `Presume.json` or `Concede.json` in the normal HSConfig path.

# Card Behavior Policy

Every deck card must be represented in the gameplan contract.

Emit `per-card <CARDID>.json` when documented VisionAI syntax can express a guide-backed
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

## Source Backing Notes

The public-doc-confirmed normal card behavior blocks include `BeforePlayCardBonus`,
`BeforeBattlecryTargetBonus`, `BeforeUseHeroPowerBonus`,
`BeforePhysicalAttackBonus`, `OnDiscoverCardBonus`, `OnChooseOneCardBonus`, and
`InHandPlayPriority`.

The repo-supported source-gap blocks are `OnAdaptCardBonus`,
`BeforeUpgradeCardBonus`, and `OnBoardPlayPriority`. Keep them visible as
supported HSConfig registry blocks, but do not describe them as confirmed in the
latest public-doc audit. They are not confirmed in the latest public-doc audit.

Per-card-every-card coverage is HSConfig rich-output repo policy. It is not the
minimal runtime-write gate and not an official HearthRanger minimum.

Guide claims may request a specific `runtime_block` only when the block is part
of the documented CardID behavior registry. Unsupported blocks stay in reports.

CardID behavior block support is source-backed and block-specific:

- `targeting_rule` claims may lower to target, play, attack, overkill, Discover, Choose One, or Hero Power blocks when the source names a matching behavior.
- `mechanic_usage` and `card_role` claims may create runtime rows only when static card text or guide text gives a clear behavior.
- `known_bad_pattern` claims stay report-only unless they map to a documented negative value row.
- `tech_slot` and `replacement_option` claims are operator context and do not become CardID runtime rows by default.

`meaningful_runtime_surface=true` means the row expresses specific guide-backed
runtime behavior. Generic generated `per-card <CARDID>.json` fallback files stay visible, but they
do not prove deep card-specific lowering.

If a claim cannot be lowered safely, keep it in
the `suppressed` rows of `card_behavior_plan_report.json` instead of inventing unsupported runtime
syntax.

Card behavior reports support `operator_summary.json`; they do not create an independent apply gate.
Do not emit `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json` in the normal HSConfig path.

## Semantic Handoff Safety

- `SOURCE_BACKED_STRONG` proves source closure only. It is necessary but not sufficient for semantic handoff.
- Read `semantic_handoff_status` and `semantic_handoff_reasons` before describing a package as semantically closed.
- Never lower generic gameplay “keep” prose into `Mulligan.json`; explicit opening-hand or Mulligan context is required.
- Reject the whole runtime row when any structured condition atom is unsupported.
- Targeting claims count as closed only when target scope and a compatible target surface are both encoded.
- Do not emit generic `InHandPlayPriority` or `BeforePlayCardBonus` rows solely to make every-card coverage appear complete.
- `reports/operator_summary.json` remains the only normal apply authority.
- `semantic_handoff_status` is diagnostic and never creates a second apply gate.

## Diagnostic Intent Taxonomy

Card intent taxonomy is diagnostic and scoring-only. It may choose stronger
values for supported per-card CardID behavior rows, but it must not create a new
runtime surface, a new apply gate, or unsupported HearthRanger syntax.

Known ShadowPriest-style semantics that should not remain generic defaults when
card text or exact card identity is available:

- Direct enemy hero burn, for example Mind Blast.
- Conditional minion-death burn, for example Mind Sear.
- Reciprocal hero burn, for example Shadowbomber and Acupuncture.
- Damage-aura amplification, for example Voidtouched Attendant.
- Self-damage resource/refill, for example Raise Dead.
- Self-damage liability body, for example Brain Masseuse.
- Opponent-damage discount tempo, for example Frenzied Felwing.
- Hero-power cost aura, for example Papercraft Angel.
- Hero-power transform, for example Darkbishop Benedictus.
- Location tempo/draw, for example Cathedral of Atonement.

These classifications explain `semantic_score.reason` and `surface_intent`
rows. They do not prove Mulligan keeps, exact combo order, targeting conditions,
or post-game tuning. Keep unsupported sequencing and timing claims report-only
unless a documented VisionAI surface can express them safely.

## Audited Card Runtime Surfaces

| Semantic family | Identity | Behavior block | Emission status |
| --- | --- | --- | --- |
| `hero_power_transform` | `SW_448 -> EX1_625t` | `BeforeUseHeroPowerBonus` | exactly one active row |
| `summon_trigger_board_engine` | Treasure Distributor or Ship's Chirurgeon | `OnBoardBonus` | one active row per card |
| `reciprocal_hero_burn` | reciprocal health effect | none | report_only |
| `metadata_only` | filename or identity metadata only | none | report_only |

Darkbishop owns no body priority and no inferred Mulligan keep. Reciprocal burn
and other state-dependent mechanics remain report-only until a documented safe
condition exists. A metadata-only CardID file is not `runtime_emitted`; only a
parsed physical payload with a non-metadata `values` row can earn that status.

- Source card: `SW_448` (Darkbishop Benedictus)
- Link: `hero_power_transform`
- Runtime owner: `EX1_625t` (Mind Spike)
- Physical row: `CardID/EX1_625t.json`

The source card causes the transform while the linked entity owns
`BeforeUseHeroPowerBonus / * / 10`. The numeric bonus is configuration policy,
not proof of optimal play.

## Physical Runtime Row Contract

| Concept | Shape | Result |
| --- | --- | --- |
| `runtime_key` | `(card_id, behavior_block, condition)` | one physical owner per runtime slot |
| `full_signature` | `(card_id, behavior_block, condition, value)` | canonical emitted-row identity |
| `duplicate_provenance` | identical full signature | merge and sort provenance |
| `conflicting_values` | same runtime key with different values | fail closed; suppress physical row |
| `physical_report_parity` | physical CardID `values` versus meaningful card-behavior report rows | exact row parity required |

Duplicate full signatures emit once while source claim IDs, source references,
and lifecycle claim IDs merge deterministically. Different values for the same
runtime key must fail closed and remain diagnostic. Physical output and
meaningful card-behavior report rows must have exact parity: every physical
CardID `values` row has one meaningful report row, and every meaningful report
row has physical output. Compare a canonical typed multiset rather than a set or
string-normalized mapping: duplicate multiplicity and JSON condition/value
types are part of the contract.

## Audited Deck-set Invariants

The read-only twelve-deck acceptance loads deck codes from the eleven-row
representative manifest plus supplemental CuteWarrior. It enforces:

- `semantic_enrichment_report.json` must prove that neither the source card nor
  a linked physical runtime owner is a spell for `OnBoardBonus` or
  `BeforeBattlecryTargetBonus`;
- physical and meaningful report rows have duplicate-preserving typed parity in
  both directions before each report row is checked for non-empty source claim
  IDs and source references;
- condition-related suppressions do not reappear as unconditional physical
  rows;
- `EX1_625t`, not `SW_448`, owns ShadowPriest's Hero Power row; reciprocal
  burn stays report-only; Treasure Distributor and Ship's Chirurgeon each own
  one audited `OnBoardBonus`;
- MechPala's three `TOY_330` sideboard modules stay metadata/readiness-only and
  the owner is not a policy Mulligan keep;
- Kingslayer wrong-owner `BeforePhysicalAttackBonus` rows stay absent, Boarlock
  has no static `Combo.json`, and Discolock has no coverage-only
  `InHandPlayPriority`;
- ImbueMage's physical non-wildcard Mulligan identities exactly match the
  readiness ledger's Mulligan surfaces.

This is pre-run contract evidence only. It proves neither HearthRanger
in-client execution nor gameplay optimality.

## Configuration Assurance

The exact fields are `load_safety`, `source_authority`, `semantic_closure`,
`in_client_behavior`, `optimality_claim_allowed`, and `runtime_gate_impact`.
Load safety does not prove in-client optimality. `in_client_behavior` remains
`not_proven_by_pre_run_contract`, `optimality_claim_allowed=false`, and
`configuration_assurance` is diagnostic and has `runtime_gate_impact=none`.

## Choice Surface Lowering

`discover_choice` may lower to `OnDiscoverCardBonus` only when the selected option card identity is resolved from source evidence and linked entity metadata. If no condition is supplied, HSConfig derives `my_discover(count(),cardid=<OPTION_CARD_ID>) > 0`.

`choose_one_choice` may lower to `OnChooseOneCardBonus` only when the selected option card identity is resolved from source evidence and linked entity metadata. HSConfig keeps the condition as `*` unless the source document supplies a documented runtime condition.

Unresolved option identity must stay visible in the `suppressed` rows of `card_behavior_plan_report.json` with `reason=unresolved_option_identity`; do not emit guessed choice rows.

`choose_one_choice` lowers to `choose_one` and is identity-gated direct. It may emit `OnChooseOneCardBonus` only when option identity is source-backed. Generic spell targets, minion positioning, repeated location activation, secret timing, and random generated-entity pools stay warning-only unless a documented card-specific VisionAI surface is added.

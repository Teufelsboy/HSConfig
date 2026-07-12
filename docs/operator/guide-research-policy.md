# Guide Research Policy

HSConfig compiles structured source claims. Codex performs the live guide research before running HSConfig, then normalizes that research with `hsconfig research-deck`.

For the normal operator entry point, start at `docs/operator/README.md`.

## Accepted Sources

- official card text
- HearthstoneJSON metadata
- current archetype guides
- current matchup guides
- current mulligan guides
- card-specific gameplay discussions

## Rejected Sources

- vague tier-list blurbs
- non-card-specific advice
- stale claims that contradict current card text
- claims that cannot be mapped to a documented runtime surface or report-only note

## Structured Source Format

Pass researched source documents with `--source-documents-json`, or pass normalized `research-deck` output with `--guide-sources-json`.

```json
[
  {
    "source_url": "https://example.invalid/deck-guide",
    "source_title": "Deck Guide",
    "source_family": "guide",
    "retrieved_at": "2026-07-06T12:00:00Z",
    "deck_name": "Example Deck",
    "archetype": "aggro_burn",
    "claims": [
      {
        "claim_kind": "mulligan_keep",
        "cards": ["CARD_ID"],
        "selector": "CARD_ID",
        "selector_kind": "card",
        "stance": "keep",
        "evidence_text_short": "Keep this card because it enables the deck plan.",
        "source_confidence": "high"
      }
    ]
  }
]
```

Accepted source document fields:

- `source_url`: stable URL or local source identifier.
- `source_title`: human-readable title for operator reports.
- `source_family`: source type such as `guide`, `mulligan_guide`, `card_text`, or `metadata`.
- `retrieved_at`: ISO timestamp used for claim freshness checks.
- `deck_name`: optional deck label used for candidate archetype matching.
- `archetype`: optional source-stated archetype or posture.
- `claims`: list of atomic claims.

Accepted atomic claim fields:

- `claim_kind`: one of the supported atomic claim kinds below.
- `cards`: concrete CardIDs affected by the claim.
- `scope`, `stance`, `selector`, `selector_kind`, `condition`, and `reason`: optional claim context.
- `evidence_text_short`: short source quote or paraphrase for reports.
- `source_confidence`: `high`, `medium`, or `low`.
- `runtime_block`, `runtime_value`: optional CardID behavior lowering hints.
- `sequence`, `timing_kind`, `operator`, and `values`: optional Combo timing fields.

A `runtime_block` or `runtime_value` hint never overrides `claim_kind`.
Runtime lowering is surface-gated: `Mulligan.json` only lowers explicit
`mulligan_keep` or `mulligan_discard`; `GlobalValues.json` only lowers
runtime-lowerable `gameplan_posture`; `Combo.json` only lowers complete
`combo_sequence`; and per-card `<CARDID>.json` only lowers CardID behavior
claim kinds. Wrong-surface claims stay suppressed or report-only with explicit
reasons.

`policy_lane` is static source policy, not runtime emission. Use
`source_contract_audit.json.claim_lifecycle_rows` for the generated trace from
source -> policy -> surface gate -> builder/router -> emitted/suppressed. A
no-block deck can still include suppressed diagnostics when a source claim has
no documented runtime surface; readiness and apply authority remain in
`operator_summary.json`.

### Claim Lifecycle End States

`source_contract_audit.json.claim_lifecycle_rows` is diagnostic-only. Each source
claim should end in one visible state:

- `emitted`: a source claim reached a runtime file.
- `suppressed`: a source claim was intentionally not emitted because the source,
  confidence, runtime evidence, or VisionAI surface did not allow it.
- `not_seen_by_builder`: the source and surface gate allowed a claim, but no
  builder/router emitted it. Treat this as implementation debt, not an operator
  apply block.

Use `operator_summary.json` for normal readiness and apply decisions. Do not use
`source_contract_audit.json` as an apply gate.

### Contract Conformance Snapshot

The contract conformance snapshot is documentation-as-code for the source
contract. It proves that each supported `claim_kind` has one policy lane,
surface-gate outcome, and diagnostic operator impact. It does not create a
second operator gate: `source_contract_audit.json` stays diagnostic and
operator_summary.json remains the normal apply authority.

`contract_spine_rows` are diagnostic. They provide the compact source -> policy -> surface gate -> builder/router -> runtime effect chain for each claim kind. They do not grant apply permission, and operator_summary.json remains the normal apply authority.

The snapshot separates unexpected contract drift from expected builder
prerequisite gaps. Unexpected contract drift means the policy matrix, surface
gate, or builder expectation disagrees and should be fixed. A builder
prerequisite gap means the surface is allowed, but the concrete row is still
missing required structure, such as a complete `Combo.json` sequence. These
gaps support no-block package generation by staying visible without becoming a
second apply gate.

For CardID behavior claims, prefer source-backed `runtime_block` when the guide
or card text clearly maps to a documented VisionAI block. Examples:

- face pressure or play timing: `BeforePlayCardBonus`
- targeted Battlecry: `BeforeBattlecryTargetBonus`
- Hero Power use: `BeforeUseHeroPowerBonus`
- attack or weapon posture: `BeforePhysicalAttackBonus`
- Overkill payoff: `BeforeOverkilledBonus`
- Discover option preference: `OnDiscoverCardBonus`

Do not request undocumented blocks. Unsupported blocks are suppressed into
reports and do not become runtime JSON.

Supported source claim kinds for normal Step1 routing are `archetype`,
`mulligan_keep`, `mulligan_discard`, `card_role`, `targeting_rule`,
`combo_sequence`, `gameplan_posture`, `hero_power_transform`,
`mechanic_usage`, `known_bad_pattern`, `tech_slot`, `replacement_option`,
`discover_choice`, and `choose_one_choice`.

`globalvalue_numeric_tuning` is accepted source evidence for explicit numeric
GlobalValues recommendations, but it is not Step1 runtime-lowerable. It must
stay report-visible with `requires_runtime_evidence` until HSTuner or another
runtime-evidence workflow owns the change. Do not introduce wildcard
`globalvalue_*` claim kinds.

Additional supported choice-claim requirements:

- `discover_choice`: exact card-specific Discover option preference; requires `option_card_id` or `option_card` plus source-backed option identity.
- `choose_one_choice`: exact card-specific Choose One option preference; requires `choice_card_id` or `choice_card` plus source-backed option identity.

Claim freshness and conflicts:

- Treat `retrieved_at` as the claim freshness anchor. Prefer current guide claims over older guide claims when both map to the same card and behavior.
- Do not use stale claims that contradict current card text or HearthstoneJSON metadata.
- Opposing atomic claims, such as keep versus discard for the same selector, must be reported in `claim_conflict_report.json`.
- Conflict reports block strong readiness until the operator resolves the source documents.

Mulligan selector support:

- Use concrete CardIDs for direct keeps or discards.
- Use `DROPn` selectors for documented curve or cost-based keeps.
- Use plus-combo selectors when the source says a keep depends on a partner card.
- Use wildcard selectors only when the source applies broadly to a known hand class.
- Use explicit discard selectors for guide-backed throws; do not infer discard from absent keep text.

Do not infer `mulligan_keep` from card importance, start-of-game effects,
deckbuilding effects, hero-power-transform text, or generic "keep" wording.
Preserve those effects as `hero_power_transform`, CardID behavior, or
report-visible contract evidence. Emit a Mulligan keep only when a current
mulligan source explicitly says the card should be kept in the opening hand.

Combo timing support:

- `combo_sequence` claims must include explicit `sequence`, `timing_kind`, `operator`, and `values` before runtime `Combo.json` emission.
- Claims without explicit order or timing stay in reports and do not become runtime rows.

GlobalValues key authority:

- `global_values_authority_matrix.json` records Step1 posture overlays and runtime-evidence-only blocked changes.
- `global_values_key_profile_report.json` records every key with `authority_category` and `board_value_component`.
- Use `gameplan_posture` for Step1 GlobalValues posture that may lower to `GlobalValues.json`.
- `globalvalue_numeric_tuning` is a valid source claim kind for explicit numeric GlobalValues recommendations. It is report-visible but Step1 runtime-blocked with `requires_runtime_evidence` until HSTuner or another runtime-evidence workflow owns the change.
- `copy_baseline` keys are copied and profiled, not tuned.
- `step1_posture_overlay_allowed` keys may change only when source posture supports them.
- `runtime_evidence_required` keys stay blocked until HSTuner or another runtime-evidence workflow owns them.

## Per-Card Depth Rule

For representative archetype breadth, use `docs/operator/archetype-fixture-matrix.json`.
Core source-backed fixtures should cover ShadowPriest, BigShaman, Discolock,
Kingslayer, and ImbueMage before broadening to the second-wave decks.

Before normal `hsconfig prepare`, Codex should try to give every deck card at
least one structured expectation. The preferred order is card-specific guide
claim, current card text/static semantics, archetype-inferred role, then
`generic_low_confidence` as the last visible fallback.

The every-card coverage rule is: every card must land in a visible lane, and
only guide-backed or source-backed static semantics can support strong guide
depth.

Claim readiness lanes:

- `guide_backed`: current source claim maps to one or more concrete deck cards.
- `source_backed_static_semantics`: card text or metadata supports a deterministic static expectation.
- `archetype_inferred`: deck-scoped posture without card-specific source support.
- `explicit_low_confidence`: source is current but weak or low confidence.
- `generic_low_confidence`: no useful source or static semantic support exists.
- `contract_gap`: the claim could not be made specific enough for the config contract.

Only `guide_backed` and `source_backed_static_semantics` can contribute toward strong guide-depth readiness.

For each card, prefer claims that answer at least one of these questions:

- keep, discard, or situational mulligan
- face, trade, friendly target, discover, weapon, location, or Hero Power usage
- combo sequence or synergy partner
- board-value posture or GlobalValues effect
- known bad pattern

## Reports

- `operator_summary.json`: operator-facing technical and semantic readiness.
- `operator_summary.json.guide_strength_summary`: compact counts for why a valid package is or is not guide-strong.
- `operator_summary.json.semantic_blockers`: grouped blocker reasons such as missing guide claims, runtime-surface gaps, combo-sequence gaps, or conflicts that keep a package at `VALID_BUT_NOT_GUIDE_STRONG`.
- `guide_builder_receipt.json`: guide-source normalization status and source counts.
- `candidate_archetypes.json`: primary and fallback archetype candidates.
- `deck_fingerprint.json`: deck multiset identity used by research normalization.
- `identity_graph_report.json`: main deck, sideboard, hero, and metadata identity.
- `guide_claim_bundle.json`: normalized claims used by the build.
- `source_evidence_index.json`: source-level summary.
- `claim_coverage_report.json`: guide-backed, static-semantics, and uncovered card counts.
- `unsupported_claims_report.json`: rejected source claims with reasons.
- `source_contract_audit.json`: per-claim and per-card explanation for why evidence did or did not lower to a runtime surface; `claim_lifecycle_rows` are diagnostic only.
- `source_claim_gap_report.json`: first missing source or lowering link per card.
- `strong_promotion_report.json`: promotion verdict and the reason a package does or does not reach `SOURCE_BACKED_STRONG`.
- `mulligan_plan_report.json`: concrete keep/discard plan before runtime compilation.
- `card_behavior_plan_report.json`: CardID routing and suppression reasons.
- `combo_plan_report.json`: exact ordered combos and suppressed combo claims.
- `global_values_authority_matrix.json`: Step1 GlobalValues overlays and runtime-only blocked changes.
- `per_card_config_readiness_report.json`: card-level lane, runtime surfaces, and first missing link.
- `guide_source_depth_report.json`: source-depth status, source families, claim kinds, and research warnings.

HSConfig does not prove gameplay improvement. It creates the best available initial config from current source claims and card semantics. HSTuner remains the post-game analysis and tuning tool.

## Next-Wave Source Autonomy

See `docs/operator/autonomous-source-builder-next.md` for the source-acquisition contract that should feed `research-deck` before future deck-only autonomy work. This document is intentionally a contract, not an implementation of web browsing or scraping.

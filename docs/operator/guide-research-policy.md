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

## Source Truth Is Not Runtime Authority

Source documents can be true and still not lower to runtime JSON. `claim_kind` is the runtime-routing authority. The surface gate decides whether a claim may
lower to `Mulligan.json`, `GlobalValues.json`, per-card `<CARDID>.json`, or
`Combo.json`. `operator_summary.json` remains the only normal apply authority.

The canonical claim lifecycle is the single diagnostic chain from source
evidence to runtime eligibility: source claim -> normalized `claim_kind` ->
semantic qualifiers -> conflict quarantine -> surface gate -> builder/router
outcome -> emitted runtime row or suppression reason. source_contract_audit.json is diagnostic; operator_summary.json remains the only normal apply authority.
Quarantined claims suppress unsafe runtime rows, stay visible in reports, and do
not block load-safe valid packages.

`Presume.json` and `Concede.json` are legacy/diagnostic VisionAI surfaces outside the normal HSConfig output path. Their absence never blocks a valid load-safe package, and their presence in a normal package is treated as drift.

Open `reports/operator_summary.json` first. Other reports explain source quality, mechanic coverage, ownership, and missing links. They do not grant apply permission.

## Single Apply Authority

reports/operator_summary.json remains the only normal apply authority.
diagnostic reports must not become apply gates: `source_contract_audit.json`,
`source_to_runtime_explainability.json`, mechanic visibility reports, source
quality reports, and claim lifecycle projections explain what happened but do
not allow or block runtime writes. default-only runtime surfaces must be
visible, not silent: a valid load-safe package may proceed with warnings, but
the reports must show whether a card is runtime-backed, source-action-needed,
diagnostic-only, or baseline-only-visible.
`source_to_runtime_explainability.json` includes per-card closure rows, and
`default_only_runtime_surface_details` summarizes default-only risk in
`operator_summary.json`; both remain diagnostic because operator_summary.json
remains the only normal apply authority.

Closure freshness is diagnostic-only. `operator_summary.json remains the only normal apply authority`; `closure_schema_current`, `cards_missing_closure`, `closure_lane_counts`, and `default_only_runtime_surface_details` explain whether a freshly generated package exposes every card's source-to-runtime state. They must not become a second runtime-write gate.

`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside
the normal HSConfig path. The normal runtime path remains `Mulligan.json`,
`GlobalValues.json`, `Combo.json`, and per-card `CARDID.json`.

## Source-To-Runtime Boundary

HSConfig separates technical load safety from source richness. A package may be
load-safe and apply-ready even when some guide claims remain diagnostic.
`reports/operator_summary.json` is the only apply authority.

`SOURCE_BACKED_STRONG` is a source-confidence label, not an apply gate.
`policy_backed_autonomous_mulligan` may prevent default-only output, but it does
not convert a claim into source-backed evidence.

Never lower these into runtime config unless the specific runtime surface is
documented and identity is resolved:

- start-of-game or deckbuilding effects as opening-hand mulligan keeps
- hero-power-transform effects as opening-hand mulligan keeps
- generated random pools as deterministic per-card behavior
- Discover or Choose One preference without exact option identity
- numeric GlobalValues tuning without runtime evidence

No-silent-default-only contract: a valid package must not hide baseline-only runtime behavior. Default-only surfaces are reported as visible quality debt through `operator_summary.json`, `default_only_runtime_surface_details`, and `source_to_runtime_explainability.json`; they are not an apply blocker unless the technical package is invalid. operator_summary.json remains the only normal apply authority.

The first compact check is `operator_summary.json.surface_status_ledger`. Every listed surface must expose whether it is source-backed, policy-backed, static-semantics-backed, warning-only, suppressed, or default-only. `default_only_runtime_surfaces` remains the compatibility list, but the ledger is the preferred operator view because it shows every surface, including non-default surfaces. Ledger rows are diagnostic-only and must keep `apply_blocking=false`.

## Source-To-Runtime Decision Rule

Source truth becomes runtime config only through `claim_kind`, the source contract matrix, and the surface gate for the target runtime file. Guide importance, archetype value, or effect relevance do not bypass this chain.

When the chain is incomplete, HSConfig should keep the claim visible in reports and still produce a load-safe package when the package is technically valid.

## Claim Family Guardrail

Every supported `claim_kind` has exactly one policy lane, one allowed runtime
surface set, one negative-boundary rule, and one diagnostic conflict family.
Changing a claim kind means updating the claim-family registry, the source
contract matrix, the runtime surface gate, the builder/router tests, and the
contract-spine sentinel together.

The guardrail is diagnostic only. It protects the source-to-runtime contract,
but it does not create another apply gate. reports/operator_summary.json
remains the only normal apply authority.

`source_advisory_gate` is warning/advisory only. It can explain source quality
or missing evidence, but it never grants, denies, or replaces runtime apply
authority.

## Semantic Qualifiers

Semantic qualifiers refine existing source claims. They do not create a second
apply path and they do not bypass `claim_kind` or surface gates.

Supported qualifier families:

- `timing`: `mulligan`, `start_of_game`, `on_play`, `delayed`, `ongoing`, `death`, `trigger`
- `zone_scope`: `hand`, `deck`, `board`, `secret`, `location`, `generated`, `graveyard`
- `target_scope`: `enemy_hero`, `friendly_minion`, `enemy_minion`, `any_minion`, `no_target`
- `option_surface`: `discover`, `choose_one`, `generated_choice`
- `state_requirements`: deck, hand, board, weapon, mana, overload, duplicate, or mechanic constraints

When source text says an effect matters but does not explicitly say opening
hand or mulligan, HSConfig must preserve effect semantics without turning the
card into a `Mulligan.json` keep.

Examples:

- Darkbishop Benedictus can preserve the Shadowform / Mind Spike effect through
  `hero_power_transform` and CardID behavior, but this does not become a mulligan keep unless a separate current mulligan source explicitly says to
  keep the card in the opening hand.
- `globalvalue_numeric_tuning` is valid source evidence for future tuning, but
  Step 1 requires runtime evidence before numeric GlobalValues changes.
- Discover and Choose One claims require exact option identity before lowering.

Warnings are follow-up work, not a runtime apply blocker.
Do not use `source_contract_audit.json` as an apply gate.

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

`operator_summary.json` remains the only normal apply authority.
`source_contract_audit.json` explains why each claim did or did not lower.
`contract_spine_rows` show the compact source -> policy -> surface gate -> builder/router -> runtime effect chain.
Warnings are follow-up work, not a runtime apply blocker.
Do not use `source_contract_audit.json` as an apply gate.

The snapshot separates unexpected contract drift from expected builder
prerequisite gaps. Unexpected contract drift means the policy matrix, surface
gate, or builder expectation disagrees and should be fixed. A builder
prerequisite gap means the surface is allowed, but the concrete row is still
missing required structure, such as a complete `Combo.json` sequence. These
gaps support no-block package generation by staying visible without becoming a
additional runtime-write gate.

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

### Policy-backed autonomous Mulligan fallback

If no source-backed keep can be emitted, HSConfig may build a small
`policy_backed_autonomous_mulligan` keep set from deterministic low-curve
pressure, draw, setup, or class-plan semantics. This keeps valid deck packages
useful and prevents default-only `Mulligan.json` output.

This fallback is not source-backed guide evidence and does not promote a deck to
`SOURCE_BACKED_STRONG`. It is visible in `mulligan_plan_report.json` and
`operator_summary.json.config_usefulness.surfaces.mulligan` as
`status=policy_backed`.

The fallback must still respect the source/contract boundary: start-of-game,
deckbuilding, highlander, odd/even, hero-power-transform, and other non-hand
effects stay out of opening-hand keeps unless a current mulligan source
explicitly says the card should be kept. Darkbishop Benedictus remains the
reference case. Cards with explicit, suppressed, or quarantined Mulligan source
intent are also excluded from policy keeps until the source intent is resolved.

### Effect semantics are not opening-hand mulligan keeps

Start-of-game, deckbuilding, and hero-power-transform effects can be important
runtime semantics without being cards to keep in the opening hand. Darkbishop
Benedictus is the reference case: the Shadowform / Mind Spike behavior belongs
in card behavior semantics, but the card itself must not become a Mulligan.json
hold unless a source explicitly describes opening-hand mulligan intent.

This split also applies to odd/even, highlander, deck-size, starting-health,
and start-in-deck effects. These effects may create CardID behavior, source
diagnostics, or report-visible expectations. They do not create mulligan keeps
from generic card importance, start-of-game text, or deckbuilding text.

operator_summary.json remains the normal apply authority.

Do not infer `mulligan_keep` from card importance, start-of-game effects,
deckbuilding effects, hero-power-transform text, or generic "keep" wording.
Preserve those effects as `hero_power_transform`, CardID behavior, or
report-visible contract evidence. Emit a Mulligan keep only when a current
mulligan source explicitly says the card should be kept in the opening hand.

Exact `mulligan_keep` claims should describe opening-hand intent. If the evidence
only describes a start-of-game effect, hero-power transform, deckbuilding rule, or
broad card importance, HSConfig may warn about a suspicious exact keep. That
warning is diagnostic only; it does not block a load-safe package.

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

## Claim-Kind Change Checklist

Changing or adding a `claim_kind` is a contract change, not a local parser tweak.
Every such change must update all of these surfaces in the same pull request:

- `SUPPORTED_ATOMIC_CLAIM_KINDS` in `src/hsconfig/source_document_model.py`
- the policy row and policy details in `src/hsconfig/source_contract_matrix.py`
- the matching surface gate in `src/hsconfig/source_document_model.py`
- the builder, router, or diagnostic path that owns the final runtime effect
- conformance and freeze coverage in `tests/test_source_contract_spine_freeze.py`
- runtime contract coverage in `tests/test_claim_kind_runtime_contract.py`

Diagnostics may explain a claim, but they must not grant or deny runtime apply.
`reports/operator_summary.json` remains the normal apply authority.

## Adding A New Claim Kind

New claim kinds must follow the same compact spine:

1. Add the atomic claim kind to `SUPPORTED_ATOMIC_CLAIM_KINDS`.
2. Add exactly one policy row in `source_contract_matrix.py`.
3. Decide the allowed surface: `mulligan`, `globalvalues`, `cardid`, `combo`, or none.
4. Add or update the matching surface-gate test.
5. Add builder/router coverage only when the VisionAI surface is documented and syntax-safe.
6. Keep report-only, runtime-evidence-required, unresolved-identity, and warning-only mechanics non-blocking.
7. Keep `operator_summary.json` as the only normal apply authority.

New claim kinds must not create an additional runtime-write gate or bypass or
replace the apply authority.

Do not add broad wildcard claim kinds such as `globalvalue_*` or prose-driven
claims that bypass the surface gates.

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

### Source Claim Quality Summary

`operator_summary.json.source_claim_quality_summary` is a compact source-depth
visibility block. It counts every-card lanes, generic-low-confidence cards,
contract-gap cards, and the next useful claim kinds. It is non-blocking:
source-quality debt explains what to improve next, but it does not replace
`operator_summary.json` as the apply authority and does not create a second
apply path. `source_contract_audit.json` remains diagnostic-only detail for
the source-to-runtime explanation.
`source_to_runtime_explainability.json` is the operator-readable projection of
the same diagnostic chain. It summarizes emitted runtime files, missing runtime
files, first missing links, and next source actions per claim/card. Its
`operator_summary.json.source_to_runtime_explainability_summary` block is
non-blocking and never grants apply permission.

- `guide_builder_receipt.json`: guide-source normalization status and source counts.
- `candidate_archetypes.json`: primary and fallback archetype candidates.
- `deck_fingerprint.json`: deck multiset identity used by research normalization.
- `identity_graph_report.json`: main deck, sideboard, hero, and metadata identity.
- `guide_claim_bundle.json`: normalized claims used by the build.
- `source_evidence_index.json`: source-level summary.
- `claim_coverage_report.json`: guide-backed, static-semantics, and uncovered card counts.
- `unsupported_claims_report.json`: rejected source claims with reasons.
- `source_contract_audit.json`: per-claim and per-card explanation for why evidence did or did not lower to a runtime surface; `claim_lifecycle_rows` are diagnostic only.
- `source_to_runtime_explainability.json`: claim/card projection that names emitted files, missing files, first missing links, and next source actions; diagnostic only.
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

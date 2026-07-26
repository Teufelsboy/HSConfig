# HSConfig ShadowPriest Semantic Closure Design

**Status:** Approved audit recommendation; implementation planning requested on 2026-07-26.

**Scope:** `C:\Users\darbo\Documents\HSConfig` only. The design changes source
classification, runtime lowering, reporting, tests, and operator documentation.
It does not apply a package, write HearthRanger runtime files, use HSTuner, add
unsupported VisionAI syntax, or claim in-client optimality.

## Problem

The current repository is structurally healthy, but three different states are
being conflated:

1. The current generator is load-safe and conservative.
2. The saved ShadowPriest package predates current contracts and fails current
   strict validation.
3. The installed runtime contains older, semantically unsafe rows.

The root causes are:

- a 40-card archetype guide can be promoted too close to an exact match for the
  target 30-card deck;
- guide Mulligan claims can lower even when the claim is not eligible for exact
  promotion;
- page chrome can become false gameplan or combo evidence;
- duplicate runtime signatures survive physical compilation;
- filename presence can overstate meaningful CardID coverage;
- package preflight does not call the same strict validation contract as
  `validate` and `apply`;
- static, persistent mechanics are under-lowered while state-dependent effects
  were historically over-lowered;
- load safety, source strength, semantic closure, and in-client optimality are
  not always presented with enough separation.

## Chosen Approach

Implement a semantic closure wave in dependency order:

1. establish exact deck identity from a successfully decoded source deckstring;
2. make exact guide identity mandatory for guide-backed Mulligan and strong
   guide promotion;
3. sanitize source-page content before matching and claim extraction;
4. preserve the existing Darkbishop CardID ownership boundary and keep
   GlobalValues dependent on a separate `gameplan_posture` claim;
5. emit only documented, statically safe CardID rows;
6. deduplicate semantic runtime signatures before and during physical compile;
7. derive readiness from parsed physical payloads;
8. make package preflight use the same strict validator inputs as `validate`
   and `apply`;
9. report load safety, source strength, semantic closure, and in-client proof
   as separate dimensions.

This is preferred over merely regenerating the package because regeneration
would retain the wrong-source Mulligan and duplicate-row defects. It is
preferred over extending the condition grammar because the required
HearthRanger syntax is not publicly proven.

## Source Identity Contract

`exact_deck_matched` is the only public-guide scope that can authorize:

- exact guide-backed Mulligan rules;
- `SOURCE_BACKED_STRONG` guide closure;
- an exact deckwide `gameplan_posture`.

The scope requires:

- a deckstring extracted from the guide content;
- successful deckstring decoding;
- equality of the decoded canonical main-deck multiset fingerprint with
  `deck_identity["deck_fingerprint"]`;
- equality of hero, format, card count, and sideboard count when those fields
  are present on both sides.

Deck name plus card-name overlap is only `archetype_matched`. It remains useful
as report context but cannot become exact runtime authority. The acquired
record stores hashes and comparison evidence, not the raw source deckstring.

## Source Content Contract

HTML acquisition prefers content inside `<main>` or `<article>`. When neither is
present it falls back to visible body text. Both paths exclude `nav`, `header`,
`footer`, `aside`, `form`, `script`, `style`, and `noscript` content.

The sanitized text is the only text used for:

- deck-name and card overlap;
- guide/decklist classification;
- source visibility;
- downstream claim extraction.

Title and publication metadata remain independently collected.

## Mulligan Contract

Public-guide `mulligan_keep` and `mulligan_discard` claims require:

```text
deck_match_scope == exact_deck_matched
promotion_eligible == true
source_visibility == full_text
source_lane == deck_matched_public_guide
```

Claims that fail this contract are suppressed with a stable reason and remain
visible in reports. They do not prevent the existing policy-backed autonomous
fallback from running. Policy-backed rows remain explicitly labeled and never
count as exact guide evidence.

Start-of-game non-hand effects such as Darkbishop Benedictus remain forbidden
as Mulligan keeps.

## Darkbishop And GlobalValues Boundary

`hero_power_transform` remains owned by the CardID/linked-identity contract:

- `SW_448.json` may contain one `BeforeUseHeroPowerBonus` row backed by the
  exact `SW_448 -> EX1_625t` identity;
- it must not contain `BeforePlayCardBonus` or `InHandPlayPriority`;
- it must not create a Mulligan keep.

The transform does not independently authorize aggressive GlobalValues.
`GlobalValues.json` changes require a separate lowerable `gameplan_posture`
claim. An archetype-only guide leaves all posture values at the validated
baseline. A neutral generated `MyHeroPowerValue=1.00` key may remain when the
runtime baseline lacks the registered key; it is not an aggressive overlay.

## Card Runtime Contract

The final ShadowPriest static surface is deliberately narrow:

| Card | Allowed active surface |
|---|---|
| `DS1_233` Mind Blast | one `BeforePlayCardBonus` |
| `REV_290` Cathedral of Atonement | one deploy `BeforePlayCardBonus`; activation remains report-only |
| `SW_446` Voidtouched Attendant | one `OnBoardBonus`; reciprocal-health timing remains report-only |
| `SW_448` Darkbishop Benedictus | one `BeforeUseHeroPowerBonus` |
| `TOY_381` Papercraft Angel | one `OnBoardBonus` |
| `TOY_518` Treasure Distributor | one `OnBoardBonus` |
| `WON_065` Ship's Chirurgeon | one `OnBoardBonus` |

These cards remain metadata/report-only until a documented condition exists:

- `CFM_637` Patches the Pirate;
- `DRG_056` Parachute Brigand;
- `GVG_009` Shadowbomber;
- `NX2_019` Mind Sear;
- `SCH_514` Raise Dead;
- `SW_444` Twilight Deceptor;
- `VAC_419` Acupuncture;
- `VAC_512` Brain Masseuse;
- `YOD_032` Frenzied Felwing.

No generic `InHandPlayPriority` is emitted solely to make a card count as
covered. Reciprocal burn remains report-only because self-health safety is not
expressible by the proven condition grammar.

Treasure Distributor and Ship's Chirurgeon use a dedicated
`summon_trigger_board_engine` semantic family. It maps only to `OnBoardBonus`;
it does not claim that either card summons a minion itself.

## Runtime Row Identity

The canonical CardID runtime signature is:

```python
(card_id, behavior_block, condition, value)
```

Equivalent rows are emitted once. Dedupe merges and sorts source claim IDs,
source references, and lifecycle claim IDs without changing the chosen runtime
value. Rows with different values are not silently merged; they are reported as
a conflict and suppressed from physical output until one value owns the
surface.

Mulligan retains its existing selector-aware signature and provenance merge.

## Validation And Reporting Contract

`validate`, package `contract-preflight`, and `apply` load:

- `globalvalues_baseline.json`;
- `globalvalues_profile.json`;
- `require_complete_package=True`;
- `require_globalvalues_profile=True`.

Preflight may report a package as contract-current only when strict validation
passes and config quality is clean. This does not modify the apply gate.
`reports/operator_summary.json` remains the only normal apply authority, and
`semantic_handoff_status` remains diagnostic.

Operator output exposes:

```json
{
  "configuration_assurance": {
    "load_safety": "proven",
    "source_authority": "exact_deck|archetype_only|partial|unproven",
    "semantic_closure": "closed|attention|insufficient_evidence",
    "in_client_behavior": "not_proven_by_pre_run_contract",
    "optimality_claim_allowed": false,
    "runtime_gate_impact": "none"
  }
}
```

Meaningful CardID readiness is derived from parsed physical payloads containing
at least one non-metadata `values` row. A filename or metadata-only file never
counts as `runtime_emitted`.

## Error Handling

- Unparseable source deckstrings are recorded as diagnostic candidates and do
  not upgrade the source scope.
- Multiple source deckstrings are allowed; exact scope is granted when at least
  one decoded candidate matches and no ambiguity exists about the matching
  candidate.
- Page extraction without `<main>` or `<article>` uses the sanitized body
  fallback.
- Unsupported or state-dependent card semantics are suppressed with stable
  reasons rather than widened to wildcard conditions.
- Conflicting duplicate runtime values are fail-closed and visible in
  config-quality output.
- Missing GlobalValues profile artifacts make strict validation and preflight
  fail consistently.

## Verification

Implementation must prove:

- exact 30-card ShadowPriest identity;
- wrong 40-card guide remains archetype-only;
- wrong-guide Mulligan claims do not lower;
- exact fixture guide claims do lower;
- page chrome does not appear in normalized text or claims;
- partial source leaves aggressive GlobalValues unchanged;
- Darkbishop preserves exactly one Hero Power row and no body/Mulligan row;
- seven cards have the allowed active surfaces above;
- nine cards remain report-only;
- physical/report runtime-row parity is exact and duplicate signatures are
  zero;
- strict validation and preflight agree;
- full pytest and contract guardrails pass;
- a fresh package is generated read-only and removed afterward;
- runtime-match performs no write;
- repository and installed skill end clean and synchronized.

## Out Of Scope

- Runtime apply or live file writes.
- HSTuner.
- Win-rate or gameplay-improvement claims.
- New condition atoms for health, damage-this-turn, graveyard, current cost,
  exact lethal, target-kill, or location activation.
- Matchup-specific tuning.
- Treating archetype overlap as exact deck evidence.

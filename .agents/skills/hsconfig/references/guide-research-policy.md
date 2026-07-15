# Guide Research Policy

Use current deck guides and data sources as strategic priors when live research is part of the request.

Every source document should be written as structured JSON and normalized with `hsconfig research-deck`. Prefer the source-builder path: `hsconfig source-manifest`, short evidence rows, `hsconfig draft-source-documents`, then `hsconfig research-deck --source-documents-json`. Runtime files stay clean; provenance and confidence stay in reports.

## Source Autopilot

`hsconfig source-autopilot` consumes compact public source-search records and writes ranked sources, source evidence rows, strict `source_documents.json`, and `source_autopilot_report.json`. The normal bridge is:

```powershell
hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" --runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --auto-source --source-search-results-json "source_search_results.json" --json
```

The bridge writes `02_source_autopilot/source_documents.json` and feeds it into the existing `research-deck` and `prepare` stages. `source-autopilot` is source-strength preflight, not runtime apply authority. `decklist_only`, snippets, `policy_fallback`, `default_runtime`, and static records without explicit supported effect semantics do not promote `SOURCE_BACKED_STRONG`; only current guide-backed, card-specific, runtime-lowerable claims or supported official static effect semantics can close the strong source-depth contract. operator_summary.json remains the only normal apply authority.

Accepted source types:

- official card text
- HearthstoneJSON metadata
- current archetype guide
- current matchup guide
- current mulligan guide
- card-specific gameplay discussion

Rejected source types:

- vague tier-list blurbs
- non-card-specific advice
- stale claims that contradict current card text
- advice that cannot be mapped to Mulligan, CardID behavior, Combo, or GlobalValues posture

## Source Lanes

- `official_static_semantics`: HearthstoneJSON, Blizzard card library, or equivalent card database facts.
- `deck_matched_public_guide`: explicit public guide for the exact list or close archetype.
- `archetype_matched_public_guide`: explicit guide for the same archetype but not exact decklist.
- `statistical_enrichment`: HSReplay/HSGuru-style aggregate or public stats surface.
- `decklist_only`: deck list or deck-code page without explicit guide claim text.
- `policy_fallback`: internal autonomous rule used to keep packages useful.
- `default_runtime`: generated default row with no source claim.

Only explicit `official_static_semantics`, explicit `deck_matched_public_guide`, and explicit `archetype_matched_public_guide` may promote claims, and only for the runtime surface they actually support. `decklist_only`, `statistical_enrichment`, `policy_fallback`, snippets, `default_runtime`, and runtime examples must not prove `SOURCE_BACKED_STRONG`.

Short evidence row shape for `--source-evidence-json`:

```json
[
  {
    "source_url": "https://example.invalid/deck-guide",
    "source_title": "Deck Guide",
    "source_family": "guide",
    "retrieved_at": "2026-07-07T12:00:00Z",
    "archetype": "aggro_burn",
    "claim_kind": "mulligan_keep",
    "card_mentions": ["Example Card"],
    "stance": "keep",
    "evidence_text_short": "Keep this card because it enables the deck plan.",
    "source_confidence": "high",
    "semantic_qualifiers": {
      "timing": "mulligan"
    }
  }
]
```

`hsconfig draft-source-documents` resolves `card_mentions` to exact deck CardIDs and writes `source_documents.json` plus `source_document_draft_report.json`. Unresolved mentions must be fixed before the source can support strong readiness.

Structured source document shape for `--source-documents-json`:

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

Normalized guide sources from `research-deck` can then be passed to `prepare` with `--guide-sources-json`.

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
- `semantic_qualifiers`, or top-level qualifier fields such as `timing`, `zone_scope`, `state_requirements`, `generation_scope`, and `deck_evaluation`: optional claim context. Use `generation_scope` for generated/random/copied/transformed cards and `deck_evaluation` for highlander, odd/even, deck-size, start-in-deck, or all-shadow-spell effects.

A `runtime_block` or `runtime_value` hint never overrides `claim_kind`.
Runtime lowering is surface-gated: `Mulligan.json` only lowers explicit
`mulligan_keep` or `mulligan_discard`; `GlobalValues.json` only lowers
runtime-lowerable `gameplan_posture`; `Combo.json` only lowers complete
`combo_sequence`; and per-card `<CARDID>.json` only lowers CardID behavior
claim kinds. Wrong-surface claims stay suppressed or report-only with explicit
reasons.

The canonical claim lifecycle is the single diagnostic chain from source
evidence to runtime eligibility: source claim -> normalized `claim_kind` ->
semantic qualifiers -> conflict quarantine -> surface gate -> builder/router
outcome -> emitted runtime row or suppression reason. source_contract_audit.json
is diagnostic; operator_summary.json remains the only normal apply authority.
Quarantined claims suppress unsafe runtime rows, stay visible in reports, and do
not block load-safe valid packages.

## Source Contract Boundary

`claim_kind`, the source contract matrix, and the surface gate decide whether source evidence may lower to runtime config. Effect relevance, guide importance, and archetype value do not bypass that chain.

`operator_summary.json` remains the normal apply authority. Source-contract reports are diagnostic only. Warnings are follow-up work, not runtime apply blockers.

normal HSConfig output must not emit `Presume.json` or `Concede.json`.

reports/operator_summary.json remains the only normal apply authority.
diagnostic reports must not become apply gates. default-only runtime surfaces
must be visible, not silent.

`Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` stay outside
the normal HSConfig path.

Optional CardID lowering fields for card-specific claims:

- `runtime_block`: documented CardID block to use, for example
  `BeforePlayCardBonus`, `OnDiscoverCardBonus`, or `BeforeOverkilledBonus`.
- `runtime_value`: numeric string to emit in the VisionAI row.
- `condition`: VisionAI condition string. Use `*` unless the source clearly
  supports a condition.

Use `runtime_block` only for guide-backed or static-semantics-backed claims. If
the exact block is uncertain, omit it and let HSConfig route or report the gap.

Supported source claim kinds for normal Step1 routing:

- `archetype`
- `mulligan_keep`
- `mulligan_discard`
- `card_role`
- `targeting_rule`
- `combo_sequence`
- `gameplan_posture`
- `hero_power_transform`
- `mechanic_usage`
- `known_bad_pattern`
- `tech_slot`
- `replacement_option`
- `discover_choice`
- `choose_one_choice`

`globalvalue_numeric_tuning` is accepted source evidence for explicit numeric
GlobalValues recommendations, but it is not Step1 runtime-lowerable. It must
stay report-visible with `requires_runtime_evidence` until HSTuner or another
runtime-evidence workflow owns the change. Do not introduce wildcard
`globalvalue_*` claim kinds.

Claim freshness and conflicts:

- Treat `retrieved_at` as the claim freshness anchor. Prefer current guide claims over older guide claims when both map to the same card and behavior.
- Do not use stale claims that contradict current card text or HearthstoneJSON metadata.
- Opposing atomic claims, such as keep versus discard for the same selector, must be reported in `claim_conflict_report.json`.
- Conflict reports block source-backed strong readiness until the source documents are resolved.
- Conflict reports do not block load-safe valid packages; quarantined claims stay report-visible and must not lower to runtime rows.

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

Before normal `hsconfig prepare`, Codex should try to give every deck card at
least one structured expectation. The preferred order is card-specific guide
claim, current card text/static semantics, archetype-inferred role, then
`generic_low_confidence` as the last visible fallback.

The every-card coverage rule is: every card must land in a visible lane, and
only guide-backed or source-backed static semantics can support strong guide
depth.

For each card, prefer claims that answer at least one of these questions:

- keep, discard, or situational mulligan
- face, trade, friendly target, discover, weapon, location, or Hero Power usage
- combo sequence or synergy partner
- board-value posture or GlobalValues effect
- known bad pattern

Confidence lanes:

- `guide_backed`: current deck guide or explicit supplied claim supports the card expectation.
- `source_backed_static_semantics`: card text or HearthstoneJSON semantics prove the behavior without a deck guide.
- `archetype_inferred`: mechanics imply a reasonable deck-plan role, but no direct guide claim exists.
- `generic_low_confidence`: HSConfig can only cover the card generically.

`operator_summary.json` is the main readiness file and single operator gate. The research contract lives under `reports/research/` and includes archetype, claims, card roles, mulligan anchors, usage expectations, known bad patterns, and GlobalValues intent.

Unsupported claims appear in `unsupported_claims_report.json`. Uncovered cards appear in `claim_coverage_report.json`.
Use `source_to_runtime_explainability.json` as the primary card-readable repair map. It is the first place to inspect emitted runtime files, missing runtime files, first missing links, closure lanes, and next source actions. `source_claim_gap_report.json` is secondary diagnostic evidence for source-depth history and must not be treated as an apply gate.

Depth reports:

- `per_card_config_readiness_report.json`: card-level lane, runtime surfaces, and first missing link.
- `guide_source_depth_report.json`: source-depth status, source families, claim kinds, and research warnings.
- `source_claim_gap_report.json`: secondary diagnostic evidence for card/source gap history.
- `strong_promotion_report.json`: promotion verdict and the reason a package does or does not reach `SOURCE_BACKED_STRONG`.

Do not infer replay performance, winrate, or postgame tuning from HSConfig outputs.

`hsconfig apply` enforces load safety, not source strength. A valid load-safe package may apply even when guide depth is weak; source-depth gaps remain visible in `operator_summary.json`, `source_claim_gap_report.json`, and `strong_promotion_report.json`.

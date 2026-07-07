# Guide Research Policy

Use current deck guides and data sources as strategic priors when live research is part of the request.

Every source document should be written as structured JSON and normalized with `hsconfig research-deck`. Runtime files stay clean; provenance and confidence stay in reports.

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

Optional CardID lowering fields for card-specific claims:

- `runtime_block`: documented CardID block to use, for example
  `BeforePlayCardBonus`, `OnDiscoverCardBonus`, or `BeforeOverkilledBonus`.
- `runtime_value`: numeric string to emit in the VisionAI row.
- `condition`: VisionAI condition string. Use `*` unless the source clearly
  supports a condition.

Use `runtime_block` only for guide-backed or static-semantics-backed claims. If
the exact block is uncertain, omit it and let HSConfig route or report the gap.

Supported `claim_kind` values:

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

Combo timing support:

- `combo_sequence` claims must include explicit `sequence`, `timing_kind`, `operator`, and `values` before runtime `Combo.json` emission.
- Claims without explicit order or timing stay in reports and do not become runtime rows.

GlobalValues key authority:

- `global_values_authority_matrix.json` records Step1 posture overlays and runtime-evidence-only blocked changes.
- `global_values_key_profile_report.json` records every key with `authority_category` and `board_value_component`.
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

Depth reports:

- `per_card_config_readiness_report.json`: card-level lane, runtime surfaces, and first missing link.
- `guide_source_depth_report.json`: source-depth status, source families, claim kinds, and research warnings.

Do not infer replay performance, winrate, or postgame tuning from HSConfig outputs.

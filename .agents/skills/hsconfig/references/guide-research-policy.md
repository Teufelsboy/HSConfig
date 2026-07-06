# Guide Research Policy

Use current deck guides and data sources as strategic priors when live research is part of the request.

Every source document should be written as structured JSON and passed with `--guide-sources-json`. Runtime files stay clean; provenance and confidence stay in reports.

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

Structured source shape:

```json
[
  {
    "source_url": "https://example.invalid/deck-guide",
    "source_title": "Deck Guide",
    "source_family": "guide",
    "retrieved_at": "2026-07-06T12:00:00Z",
    "claims": [
      {
        "claim_kind": "mulligan_keep",
        "cards": ["CARD_ID"],
        "stance": "keep",
        "evidence_text_short": "Keep this card because it enables the deck plan.",
        "source_confidence": "high"
      }
    ]
  }
]
```

Optional CardID lowering fields for card-specific claims:

- `runtime_block`: documented CardID block to use, for example
  `BeforePlayCardBonus`, `OnDiscoverCardBonus`, or `BeforeOverkilledBonus`.
- `runtime_value`: numeric string to emit in the VisionAI row.
- `condition`: VisionAI condition string. Use `*` unless the source clearly
  supports a condition.

Use `runtime_block` only for guide-backed or static-semantics-backed claims. If
the exact block is uncertain, omit it and let HSConfig route or report the gap.

Supported `claim_kind` values:

- `mulligan_keep`
- `mulligan_discard`
- `card_role`
- `targeting_rule`
- `combo_sequence`
- `gameplan_posture`
- `hero_power_transform`
- `mechanic_usage`

## Per-Card Depth Rule

Before normal `hsconfig prepare`, Codex should try to give every deck card at
least one structured expectation. The preferred order is card-specific guide
claim, current card text/static semantics, archetype-inferred role, then
`generic_low_confidence` as the last visible fallback.

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

The research contract lives under `reports/research/` and includes archetype, claims, card roles, mulligan anchors, usage expectations, known bad patterns, and GlobalValues intent.

Unsupported claims appear in `unsupported_claims_report.json`. Uncovered cards appear in `claim_coverage_report.json`.

Depth reports:

- `per_card_config_readiness_report.json`: card-level lane, runtime surfaces, and first missing link.
- `guide_source_depth_report.json`: source-depth status, source families, claim kinds, and research warnings.

Do not infer replay performance, winrate, or postgame tuning from HSConfig outputs.

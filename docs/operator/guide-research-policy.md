# Guide Research Policy

HSConfig compiles structured source claims. Codex performs the live guide research before running HSConfig.

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

Pass this file with `--guide-sources-json`.

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

Supported `claim_kind` values are `mulligan_keep`, `mulligan_discard`, `card_role`, `targeting_rule`, `combo_sequence`, `gameplan_posture`, `hero_power_transform`, and `mechanic_usage`.

## Reports

- `guide_claim_bundle.json`: normalized claims used by the build.
- `source_evidence_index.json`: source-level summary.
- `claim_coverage_report.json`: guide-backed, static-semantics, and uncovered card counts.
- `unsupported_claims_report.json`: rejected source claims with reasons.
- `mulligan_plan_report.json`: concrete keep/discard plan before runtime compilation.
- `card_behavior_plan_report.json`: CardID routing and suppression reasons.
- `combo_plan_report.json`: exact ordered combos and suppressed combo claims.
- `global_values_authority_matrix.json`: Step1 GlobalValues overlays and runtime-only blocked changes.

HSConfig does not prove gameplay improvement. It creates the best available initial config from current source claims and card semantics.

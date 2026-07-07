# Autonomous Source Builder Next Wave

HSConfig can already build a valid initial package from deck input. It reaches `SOURCE_BACKED_STRONG` when current structured guide sources provide enough card-specific, runtime-lowerable claims.

The next autonomy improvement is not another runtime surface. It is stronger source acquisition before `research-deck` and `prepare`.

## Input

- deck name
- deck code
- optional HS deck id
- optional HDT deck id

## Required Output

The source builder must emit `source_documents.json` with:

- `card_role` claims for every deck card that would otherwise be `generic_low_confidence`
- `mulligan_keep` or explicit non-keep evidence for mulligan anchors
- `targeting_rule` claims for cards whose expected target can be source-backed
- `mechanic_usage` claims only when the mechanic and runtime block are documented and source-supported
- `combo_sequence` claims only for exact sequence evidence
- `globalvalue_*` claims only when they are pre-game posture claims, not runtime performance tuning

## Fail-Closed Rules

- Do not infer gameplay improvement.
- Do not infer replay, winrate, or post-run tuning.
- Do not lower vague guide text into runtime config.
- Do not emit normal-path `Presume.json` or `Concede.json`.
- Keep unsupported claims visible in reports rather than silently applying them.

## Success Criteria

- `hsconfig research-deck` consumes the generated source documents without schema errors.
- `hsconfig prepare` produces `VALID_PACKAGE`.
- `source_claim_gap_report.json` has fewer blocked cards than deck-only static semantics.
- `strong_promotion_report.json` explains whether the package is ready or which card/source link is missing first.

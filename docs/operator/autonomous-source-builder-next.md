# Autonomous Source Builder Next Wave

HSConfig can already build a valid initial package from deck input. It reaches `SOURCE_BACKED_STRONG` when current structured guide sources or qualifying `evergreen_wild_archetype` sources provide enough card-specific, runtime-lowerable claims.

The current lightweight autonomy bridge is `hsconfig source-autopilot` or `hsconfig configure --auto-source --source-search-results-json ...`. The next improvement is stronger source acquisition before those compact records are handed to `source-autopilot`, not another runtime gate or runtime surface.

## Input

- deck name
- deck code
- optional HS deck id
- optional HDT deck id

## Required Output

The source builder must emit compact public source-search records that `source-autopilot` can turn into `source_documents.json` with:

- `card_role` claims for every deck card that would otherwise be `generic_low_confidence`
- `mulligan_keep` or explicit non-keep evidence for mulligan anchors
- `targeting_rule` claims for cards whose expected target can be source-backed
- `mechanic_usage` claims only when the mechanic and runtime block are documented and source-supported
- `combo_sequence` claims only for exact sequence evidence
- `gameplan_posture` claims for GlobalValues posture intent only when they are pre-game posture claims, not runtime performance tuning

## Fail-Closed Rules

- Do not infer gameplay improvement.
- Do not infer replay, winrate, or post-run tuning.
- Do not lower vague guide text into runtime config.
- Do not emit normal-path `Presume.json` or `Concede.json`.
- Keep unsupported claims visible in reports rather than silently applying them.

## Success Criteria

- `source-autopilot` reports `strong_candidate=false` for decklist-only/static inputs and only reports `strong_candidate=true` for current guide-backed or qualifying `evergreen_wild_archetype` card-specific runtime-lowerable evidence.
- `hsconfig research-deck` consumes the generated source documents without schema errors.
- `hsconfig prepare` produces `VALID_PACKAGE`.
- `source_claim_gap_report.json` has fewer blocked cards than deck-only static semantics.
- `strong_promotion_report.json` explains whether the package is ready or which card/source link is missing first.

# Autonomous Source Builder Next Wave

HSConfig can already build a valid initial package from deck input. Strategic
`SOURCE_BACKED_STRONG` authority requires current exact-deck-matched guide
claims acquired through `live_http` with `live_verified` provenance and a
matching strategic receipt. Supported static semantics may close deterministic
identity, role, and mechanical effect claims.

`evergreen_wild_archetype` evidence may support only deterministic/static non-strategic closure; it can never authorize strategic Combo, strategic `SOURCE_BACKED_STRONG`, or a verified strategic receipt.

The current lightweight autonomy bridge is `hsconfig source-autopilot` or `hsconfig configure --auto-source --source-search-results-json ...`. The next improvement is stronger source acquisition before those compact records are handed to `source-autopilot`, not another runtime gate or runtime surface.

## Source Candidate Plan

`source_candidate_plan.json` is the deterministic pre-acquisition plan. It lists registry candidate URLs, explicit URL ordering, public-search query suggestions, card-level claim targets, and the first missing source action. It is diagnostic acquisition guidance only: it cannot promote, block apply, write runtime config, or replace `reports/operator_summary.json`.

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

- `source-autopilot` reports `strong_candidate=false` when strategic claims lack current exact-deck-matched, live-verified guide receipts. Evergreen evidence may improve diagnostic or deterministic/static non-strategic closure, but it does not provide strategic candidate authority.
- `hsconfig research-deck` consumes the generated source documents without schema errors.
- `hsconfig prepare` produces `VALID_PACKAGE`.
- `source_claim_gap_report.json` has fewer blocked cards than deck-only static semantics.
- `strong_promotion_report.json` explains whether the package is ready or which card/source link is missing first.

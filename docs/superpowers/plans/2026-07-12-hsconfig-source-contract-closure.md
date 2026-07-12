# HSConfig Source Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Close the HSConfig Source-/Contract-Gate gaps so every valid deck still produces a load-safe package, while runtime JSON is emitted only from explicit, documented VisionAI-compatible claim kinds.

**Architecture:** Keep the existing HSConfig architecture. `source_document_model.py` remains the source of truth for claim-kind normalization and runtime-surface lowering. Tests lock the four VisionAI surfaces: Mulligan, GlobalValues, CardID, and Combo. Docs explain that `globalvalue_numeric_tuning` is valid source evidence but Step1 report-only until runtime evidence exists.

**Tech Stack:** Python package in `src/hsconfig`, pytest tests, Markdown operator docs, no new dependencies.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Do not add dependencies or a new orchestrator.
- Do not block valid deck package generation because guide/source confidence is weak.
- `VALID_PACKAGE` means runtime package is technically load-safe, not that gameplay quality is proven.
- `SOURCE_BACKED_STRONG`, `STATIC_SEMANTICS_USABLE`, and `VALID_BUT_NOT_GUIDE_STRONG` are confidence/source-depth labels, not runtime gates.
- `claim_kind` controls runtime lowering. Free-text guide phrases must not create runtime behavior by themselves.
- Start-of-game, deckbuilding, deck-state, and hero-power-transform cards must not become Mulligan keeps unless a true hand-required keep is explicitly supported.
- `globalvalue_numeric_tuning` is a valid claim kind, but Step 1 must not write numeric GlobalValues tuning from it without runtime evidence.
- ShadowPriest/Darkbishop Benedictus regression must preserve the hero-power/Mind-Spike effect while keeping Darkbishop out of `Mulligan.json`.

## Tasks

- [x] Add surface-gate contract tests for `globalvalue_numeric_tuning`, `gameplan_posture`, wrong-surface protection, and start-of-game non-hand role suppression.
- [x] Expand `START_OF_GAME_NON_HAND_EFFECT_ROLES` for common Wild deck-state and deckbuilding modifiers.
- [x] Strengthen ShadowPriest E2E assertions so Darkbishop effect semantics remain visible while `SW_448` stays out of `Mulligan.json`.
- [x] Correct operator docs and skill guidance around `globalvalue_numeric_tuning`, claim-kind-driven runtime lowering, and no-block behavior.
- [x] Run targeted and broad verification before merge/push.

## Acceptance Criteria

- `globalvalue_numeric_tuning` remains a supported claim kind.
- `globalvalue_numeric_tuning` cannot lower to Step1 `GlobalValues.json`; reason is `requires_runtime_evidence`.
- `gameplan_posture` can still lower to `GlobalValues.json` when runtime-lowerable.
- `mulligan_keep` and `mulligan_discard` remain the only Mulligan runtime claim kinds.
- Start-of-game non-hand effect roles suppress mistaken Mulligan keeps.
- Darkbishop Benedictus is not held in `Mulligan.json`.
- Darkbishop/Mind Spike semantics remain visible in ShadowPriest contract/report output.
- Representative Wild decks still produce `VALID_PACKAGE` and load-safe apply behavior.
- Docs and skill instructions match the code.

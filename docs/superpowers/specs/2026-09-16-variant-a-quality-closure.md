# Variant A: lean quality closure

Approved by the user on 2026-09-16: implement, commit, push, and reconcile local and GitHub state.

## Outcome

An ordinary request supplies a deck name and code, optionally HS/HDT identifiers. The existing skill researches the actual list, produces one defensible candidate, obtains one independent review, validates it, and completes the existing guarded live or preview path. Development CI is not a per-deck prerequisite. A source-backed start configuration is not proof of optimal play, client loading, or improved results.

## In scope

1. Reject provably impossible supported conditions; accept provably disjoint matchup decisions. Keep unknown conditions conservative.
2. Reject clearly invalid card-type/runtime-block combinations using sealed source metadata. Preserve deliberate ownership restrictions.
3. Preserve authored within-surface order where runtime evaluates ordered values. Make quality intent and change accounting agree with emitted order. Preserve duplicate provenance and historical-package validation.
4. Strengthen the existing independent reviewer instructions for source freshness and exact-list relevance, evidence versus inference, all 38 GlobalValues decisions, magnitude justification, actual emitted order, and critical decisions that are encoded, delegated, or unsupported. No new schema, review framework, or candidate tournament.
5. Exercise the current quality route for the eleven supplied decks, including MechPala's actual Zilliax sideboard, plus focused intake/unsupported-mechanic boundaries. Fixtures prove contracts, not gameplay or current source freshness.
6. Observe the existing 300-second integration timeout before changing it; repair only a demonstrated cause. Preserve meaningful tests and existing gates.
7. Keep visible deck names human-readable, internal immutable identities intact, installed skill consistent, and productive runtime/profile state protected. Complete normal Git integration and verify the exact pushed commit's existing CI jobs.

## Out of scope

No replay/HDT parsing, HSTuner, win-rate or optimality certification, new package schema/migration, new release or retagging, security-setting changes, broad cache deletion, or manual productive runtime rewrites. The eleven examples are acceptance cases, not permission to overwrite eleven productive installations.

## Acceptance

- Focused regression tests demonstrate the audited defects before fixes and pass after fixes.
- Normal quality validation/compiler coverage includes all eleven exact catalog inputs and real sideboard identities; the guarded apply/match/resume integration completes cleanly.
- Independent review has no unresolved blocking findings.
- Skill source and installed bytes match after guarded installation if changed.
- Final Git state is clean, local main equals origin/main, no task branch/worktree/stash leftovers, and the four existing CI jobs pass on that exact commit.
- Formal `final_release_ready`, actual client loading, gameplay quality, and an objectively optimal config are not claimed without their separate evidence.

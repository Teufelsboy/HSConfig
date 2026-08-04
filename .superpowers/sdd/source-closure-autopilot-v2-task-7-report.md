# Task 7 Report: Final Verification, Diff Audit, And Push

Status: DONE_WITH_FINAL_REVIEW_FIXES

## Scope Completed

- Ran Task 7 focused contract and authority suites.
- Ran full pytest after the final source-autopilot, source-acquisition, and source-scope fixes.
- Ran final read-only review and addressed its Important finding.
- Hardened the source-scope sentinel so `hsreplay`, `hs_replay`, and `hs-replay` are all forbidden in `src/hsconfig`.
- Aligned Evergreen Wild guide wording in operator docs and the repo skill reference.
- Aligned the same Evergreen Wild wording in the normal operator README, source-builder workflow, and autonomous-source-builder-next docs after final re-review.
- Removed the committed Task 6 report trailing blank line that made branch-range `git diff --check` fail.
- Synced the installed HSConfig skill after repo skill reference changes.

## Review Findings Resolved

1. Important: `tests/test_scope_boundaries.py` only guarded `hsreplay`.
   - Fix: added `hs_replay` and `hs-replay` spellings to the sample matrix and updated the regex to `hs[\s_-]*replay`.
   - Red evidence: `python -m pytest tests/test_scope_boundaries.py::test_scope_guard_terms_cover_likely_source_spellings -q` failed before the regex change.
   - Green evidence: the focused scope tests passed after the regex change.
2. Minor: stale "only current guide-backed" wording conflicted with `evergreen_wild_archetype`.
   - Fix: updated `docs/operator/guide-research-policy.md` and `.agents/skills/hsconfig/references/guide-research-policy.md`.
3. Minor: Task 6 report had an extra blank line at EOF.
   - Fix: removed the extra blank line.
4. Re-review follow-up: active operator docs still had current-only wording.
   - Fix: updated `docs/operator/README.md`, `docs/operator/source-builder-workflow.md`, and `docs/operator/autonomous-source-builder-next.md`.
   - Re-review result: stale-doc minor resolved, no new Critical/Important issues, ready to merge.

## Verification Evidence

1. Targeted Task 7 contract suite:
   `python -m pytest tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_claim_kind_runtime_contract.py tests/test_card_behavior_router.py tests/test_universal_wild_no_block_matrix.py -q`
   Result: `148 passed in 25.59s`
2. Targeted authority/docs suite:
   `python -m pytest tests/test_docs_active_path.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_source_contract_conformance.py tests/test_contract_spine_sentinel.py -q`
   Result: `95 passed in 0.94s`
3. Review-fix docs/scope/skill suite:
   `python -m pytest tests/test_scope_boundaries.py tests/test_docs_active_path.py tests/test_skill_files.py -q`
   Result: `99 passed in 0.45s`
4. Full suite before review fixes:
   `python -m pytest -q`
   Result: `1451 passed, 11 skipped in 244.37s`
5. Full suite after review fixes:
   `python -m pytest -q`
   Result: `1451 passed, 11 skipped in 251.25s`
6. Full suite after final operator-doc fixes:
   `python -m pytest -q`
   Result: `1451 passed, 11 skipped in 240.34s`
7. Installed skill sync:
   `python scripts/sync_installed_skill.py --check`
   Result: `HSConfig skill is in sync at the configured Codex skill root`
8. Diff whitespace:
   `git diff --check c4c8fb8`
   Result: exit 0
9. Source-scope scan:
   `rg -n "hsreplay|hs_replay|hs-replay|HDT parsing|Power\.log|\.hdtreplay|\.hsreplay|winrate|post-game|postgame" src\hsconfig`
   Result: no matches

## Constraints Preserved

- HSConfig remains pre-run only.
- No HSReplay/HDT/Power.log/post-game/winrate code was added under `src/hsconfig`.
- `operator_summary.json` remains the only normal apply authority.
- Source closure and closure profiles remain diagnostic-only.
- Darkbishop Benedictus remains effect-not-mulligan.
- Valid decks remain non-blocking when guide depth is weak.

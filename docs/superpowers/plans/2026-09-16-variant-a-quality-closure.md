# Variant A Quality Closure Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development, with focused TDD and independent task reviews.

**Goal:** Close demonstrated quality defects and deliver the existing lean deck workflow with clean, synchronized Git state.

**Architecture:** Extend existing schema-3 validation and serializers; retain the single-candidate route, sealed context and guarded writer. No replacement architecture.

**Tech stack:** Python 3.11, pytest, existing HSConfig compiler/controller, Git/GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-16-variant-a-quality-closure.md`.

## Global Constraints

- Preserve exact deck/CardID identity, all 38 GlobalValues decisions, every-card gameplan, strict JSON, row-level provenance, authority validation and recovery.
- No new schema, candidate tournament, replay/HDT parsing, tuning, or productive runtime writes in this development task.
- Use exact catalog inputs; distinguish static/fixture validation from client/gameplay evidence.
- Do not weaken gates, count timeouts as passes, rewrite history, delete unrelated work, or create release-readiness claims.
- Use `apply_patch` for edits. Run focused tests while iterating; coordinate heavy runs through the controller.
- The controller owns Git integration and final push. Implementers commit only their owned, reviewed scope; never push or spawn agents.
- Work in `C:\Users\darbo\Documents\HSConfig` on the task branch. Known test Python: `C:\Users\darbo\AppData\Local\Programs\Python\Python311\python.exe`.

## Task 1: Observe the integration timeout

**Own:** private diagnostic wrapper/report under this plan's ignored SDD workspace; no production edits before evidence. Existing target: `tests/test_lean_package_workflow.py::test_quality_live_flow_installs_matches_and_resumes_without_reapply`.

1. Record pytest version/plugins and monotonic setup/call/teardown, runtestloop, sessionfinish and `pytest.main` return timestamps. Add bounded faulthandler stacks using an external wrapper only.
2. Execute exactly once with the existing interpreter/environment and unchanged 300-second `_run_bounded_process` cap. Do not first clear temp directories, disable plugins, or change retention/timeouts.
3. Report return code, elapsed time, timeout flag and stacks. Separate test work, pytest finalization and launcher completion.
4. If a cause is demonstrated, propose the narrowest repair and affected tests; implementation is Task 5. No invented root cause when inconclusive.

## Task 2: Correct rule semantics in the existing quality route

**Own:** `src/hsconfig/condition_format.py`, `starter_candidate.py`, `runtime_row_identity.py`, directly required compiler/domain call sites, focused existing tests and new `tests/test_quality_rule_semantics.py`.

1. RED: exercise real full schema-3 validation and serializers using the existing quality fixture. Cases: `coin AND nocoin` rejected; disjoint mage/warrior hold/discard accepted; intersecting class lists rejected; impossible class conjunction rejected; hand dependencies remain conservative; non-hero-power `TOY_518` with `BeforeUseHeroPowerBonus` rejected.
2. RED: same CardID block `coin -> -12` then `* -> +12` retains that order, reversal differs; same-action Mulligan preserves input order; GlobalValues order-only changes alter intent/change accounting while emitted order remains unchanged. Assert actual emitted arrays and intent values, not source text.
3. Implement bounded satisfiability/overlap reasoning only for understood atoms. Mixed operators with undocumented precedence must not be interpreted optimistically. No general solver or unsupported grammar expansion.
4. Apply source metadata prerequisites only where documented and unambiguous. Keep curated runtime owner constraints; do not infer extra hero-power identities.
5. Preserve authored ordering within each runtime surface, deterministic serialization for the same input, duplicate provenance and conflict detection. Keep historical validation compatible through existing route distinctions where required; do not silently invalidate previous installed packages.
6. Run new tests plus relevant condition, candidate, row-identity and serializer regressions, using bounded execution. Self-review and commit. Report precise RED/GREEN receipts and historical compatibility decisions.

## Task 3: Cover all supplied decks through quality validation

**Own:** new `tests/test_quality_deck_catalog.py`, shared helpers under `tests/` only if genuinely needed, existing quality tests only for fixture reuse. Do not modify production code unless a concrete failure is returned to the controller.

1. Use all eleven `matrix_role=representative` entries in `docs/operator/audited-deck-catalog.json`, with the pinned source snapshot used by audited-deck acceptance. Preserve CuteWarrior as the separate twelfth catalog deck.
2. Build actual schema-3 contexts and valid single candidates, validate and compile through production code. Verify exact deck/HS/HDT identity, 30 main cards, no missing source IDs, every-card disposition and all 38 GlobalValues decisions.
3. Explicitly verify MechPala's owner `TOY_330` and sideboard `TOY_330t95`, `TOY_330t98`, `TOY_330t11`; do not substitute an E.T.C. fixture. Verify Kingslayer is not treated as Kingsbane. Preserve warnings/unsupported mechanics as honest limitations.
4. Include a non-30-card supported deck and class/name boundary cases only where existing tests leave a meaningful gap. Keep tests contract-level and fast; do not perform eleven full installation transactions or network research.
5. Ensure negative expectations would catch missing identity/disposition/sideboard protection rather than mirroring implementation. Run focused tests, self-review, and commit.

## Task 4: Strengthen the existing skill review without workflow expansion

**Own:** `src/hsconfig/resources/codex_skill_bundle.json`, relevant operator docs/README only, existing behavioral skill tests. Main must read skill-creator and writing-skills before authorizing edits.

1. Pressure-test the existing reviewer instructions with a concrete candidate containing stale/archetype-only evidence, unjustified GlobalValues magnitude, and an unsupported critical mechanic. Record what the consuming agent misses before editing.
2. Amend the existing review instructions, not the runtime schema: exact-list and date/patch applicability, evidence versus inference per material decision, all changed GlobalValues and magnitudes, actual compiled rule order, critical encoded/delegated/unsupported strategy.
3. State clearly that unknown or unsupported mechanics cannot earn unsupported optimality claims. Keep one candidate and one review; do not add a routine CI gate or extra operator inputs. Preserve concise normal usage and human visible deck names.
4. Repeat the same behavioral pressure scenario with the changed skill and verify the concerns are caught. Run existing bundle integrity/installer regression tests. Do not grep prose as a substitute for behavior.
5. Self-review and commit. Guarded installed-skill update is the controller's integration responsibility after review.

## Task 5: Repair the measured completion failure and integrate regressions

**Own:** only files causally identified by Task 1, plus covering tests. Exact ownership must be recorded before dispatch; if Task 1 completes cleanly, retain its evidence and do not invent a fix.

1. Reproduce the measured failure with a focused regression before a code change. Preserve process caps and meaningful gate coverage.
2. Implement the smallest cause-based repair. A pytest cleanup/environment issue must not become a runtime-controller rewrite; a controller issue must not be hidden by disabling cleanup/plugins.
3. Run the unchanged guarded install/match/resume test to clean process completion, plus the new semantic/catalog tests and existing affected authority tests.
4. Reconcile CI risks already fixed by unpublished commits without duplicating their changes. Self-review and commit only if a change was necessary.

## Task 6: Review, install, publish and reconcile

**Own:** root Git/installed-skill coordination; final reviewer is read-only.

1. Run whole-branch independent review including the pre-existing eleven unpublished commits where relevant to readiness. Resolve blocking findings with a scoped implementer and one reviewed fix wave.
2. Run appropriate local final checks and inspect diff. Verify protected runtime/profile baseline. Install changed embedded skill using its guarded installer and verify exact installed bytes; never manually overwrite both copies.
3. Fast-forward main from the task branch; normal push only after fresh remote checks. No force push, release, tag rewrite, or security-setting changes.
4. Observe existing `contract`, `test`, `package`, and `security` CI jobs on the exact final commit, addressing actual failures without weakening gates.
5. Fetch/prune and prove main equals origin/main, clean tracked/untracked state, no task branch/worktree/stash leftovers. Remove only this task's validated scratch artifacts after extracting ledger decisions.
6. Hand off the actual outcome and limitations. A remaining failing/in-progress CI job means not fully ready; static fixtures never prove optimal gameplay.

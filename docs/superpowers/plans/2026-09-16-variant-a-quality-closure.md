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
- Work in the existing HSConfig checkout on the task branch. Resolve the checkout root and configured Python 3.11 interpreter from the local environment; do not embed operator paths in implementation code.

## Task 1: Observe the integration timeout

**Own:** private diagnostic wrapper/report under this plan's ignored SDD workspace; no production edits before evidence. Existing target: `tests/test_lean_package_workflow.py::test_quality_live_flow_installs_matches_and_resumes_without_reapply`.

1. Record pytest version/plugins and monotonic setup/call/teardown, runtestloop, sessionfinish and `pytest.main` return timestamps. Add bounded faulthandler stacks using an external wrapper only.
2. Execute exactly once with the existing interpreter/environment and unchanged 300-second `_run_bounded_process` cap. Do not first clear temp directories, disable plugins, or change retention/timeouts.
3. Report return code, elapsed time, timeout flag and stacks. Separate test work, pytest finalization and launcher completion.
4. If a cause is demonstrated, propose the narrowest repair and affected tests; implementation is Task 5. No invented root cause when inconclusive.

## Task 2: Correct rule semantics in the existing quality route

**Own:** `src/hsconfig/condition_format.py` (new pure reasoning helpers only), `starter_candidate.py`, `live_start_controller.py`, new `quality_candidate_admission.py` if needed for a focused pure validator, `tests/test_quality_rule_semantics.py`, focused controller/historical tests. Historical serializers, schema and goldens remain unchanged.

1. RED: exercise real full schema-3 validation followed by new admission checks with the existing quality fixture. Cases: `coin AND nocoin` rejected; disjoint mage/warrior hold/discard accepted; intersecting class lists rejected; impossible class conjunction rejected; hand dependencies remain conservative; non-hero-power `TOY_518` with `BeforeUseHeroPowerBonus` rejected.
2. RED: CardID `coin -> -12` then `* -> +12` requires revision if compilation reverses that overlapping pair; disjoint coin/nocoin rows remain accepted. Same-action Mulligan ordering is not a conflicting action and need not be rejected. Reject hidden GlobalValues baseline order-only changes and overlapping different-value multi-row permutations even when neither equals baseline; accept disjoint/identical-value harmless cases. Assert actual emitted arrays and rejection behavior.
3. Add a pure `validate_quality_candidate_admission(candidate, context)` entry, called only for schema-3 candidates inside `_candidate_validation_finding`, before a NEW validation receipt can be minted. Use stable finding codes in `STARTER_CANDIDATE_FINDING_CODES`. Do not add caller-selectable strict/legacy flags or invoke new admission from historical package, review-facts, derivation or runtime reconstruction.
4. Implement bounded satisfiability/overlap reasoning only for understood atoms, leaving historical `classify_runtime_condition` semantics unchanged. Mixed operators with undocumented precedence remain conservative and must not be interpreted optimistically. Apply source metadata prerequisites only when unambiguous; keep curated owners. No general solver or grammar expansion.
5. Extend `_mulligan_conditions_overlap` monotonically for provably disjoint classes; accepted historical plans/receipts must remain byte-identical. For an already-charged rejected session whose only former conflict is now valid, preserve its old diagnostic under the existing charged-rejection state, never mint authority or reset its budget. Test that boundary. Keep golden files unchanged.
6. Run new tests plus relevant conditions, candidate, historical compatibility, receipt/authority and focused controller-admission regression tests. Preserve existing canonical rows, duplicate provenance and digest projections. Self-review and commit. Report precise RED/GREEN receipts. Existing accepted packages are grandfathered; do not claim expert/legacy paths now meet the new admission policy.

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
2. Amend review instructions only where the baseline behavior demonstrates an omission. Baseline evaluation on 2026-09-16 caught all seeded risks, so do not add redundant reminders. Document the new admission restriction (disjoint conditions instead of ambiguous priorities) in the existing normal-workflow reference, without schema changes.
3. State clearly that unknown or unsupported mechanics cannot earn unsupported optimality claims. Keep one candidate and one review; do not add a routine CI gate or extra operator inputs. Preserve concise normal usage and human visible deck names.
4. Repeat the same behavioral pressure scenario with the changed skill and verify the concerns are caught. Run existing bundle integrity/installer regression tests. Do not grep prose as a substitute for behavior.
5. Self-review and commit. Guarded installed-skill update is the controller's integration responsibility after review.

## Task 5: Repair the measured completion failure and integrate regressions

**Own:** `src/hsconfig/live_start_controller.py` (prepublication gate and fake-plan calls only), `src/hsconfig/apply_gate.py`, `src/hsconfig/deck_input_verification.py`, `src/hsconfig/runtime_apply.py` (optional carrier forwarding in `plan_apply_package` / `_resolve_allowed_apply_gate` only), new `tests/test_quality_apply_snapshot.py` and directly affected verifier/gate tests. No runtime writer, recovery or schema changes.

1. Task 1 observed a genuine secondary legacy cardxml web bootstrap inside quality finalization. RED: a real quality apply-gate evaluation with the legacy decoder forbidden must currently fail; do not mock away the production defect. Use genuine validated frozen inputs and a real compiled quality package.
2. The controller's prepublication gate has an active lease/current session. For quality only, pass the physically loaded `FrozenCompilerInputs`, checking its manifest digest against the session-bound expected manifest. Do not derive a session path from package JSON or treat `ValidatedInputSnapshotManifest` as full snapshot bytes.
3. Add an optional internal frozen-input argument to the shared gate. When present, require the exact quality authority and validate the package approval against the frozen carrier using existing `_validate_single_candidate_request_authority` (which rebuilds the sealed context). Failed binding returns `deck_input_not_verified`, with no fallback. Reconstruct the validated card snapshot from frozen `full_cards`, `collectible_cards`, `quality_inputs`; use `decode_deck_code_from_snapshot` to recompute exact deck identity. Keep existing persisted-manifest/summary/recomputed parity and every other strict/derivation/source/runtime gate.
4. When the optional argument is absent, retain the existing legacy/expert verifier unchanged. The normal controller reaches the gate both directly and through `_plan_and_install_prepublication_receipt -> plan_apply_package -> _resolve_allowed_apply_gate`; pass the same bound carrier through that fake-plan path. Do not broaden the actual writer or lease APIs. Test both paths with legacy decoding forbidden.
5. Focused negatives: changed deck code/main count/DBF/CardID; missing/conflicting snapshot mapping or altered blob/hash; resealed package context with wrong DBF mapping but unchanged frozen carrier; crossed session/manifest/context/candidate binding; persisted/summary parity mismatch; route-label crossing. Preserve hero/cardinality and real sideboard identity checks. Assert no legacy fallback on binding failure and unchanged legacy invocation when the carrier is absent.
6. Run focused gate/authority tests and then the unchanged guarded install/match/resume target once under its existing 300-second cap. Observe phases/stacks as needed. Do not claim the secondary-data repair cures the later guarded-validation cost or remote CI timeout unless measured. No blind timeout increases, plugin disabling, cleanup shortcuts or gate removal. Self-review and commit; report remaining measured latency honestly.

## Task 6: Review, install, publish and reconcile

**Own:** root Git/installed-skill coordination; final reviewer is read-only.

1. Run whole-branch independent review including the pre-existing eleven unpublished commits where relevant to readiness. Resolve blocking findings with a scoped implementer and one reviewed fix wave.
2. Run appropriate local final checks and inspect diff. Verify protected runtime/profile baseline. Install changed embedded skill using its guarded installer and verify exact installed bytes; never manually overwrite both copies.
3. Fast-forward main from the task branch; normal push only after fresh remote checks. No force push, release, tag rewrite, or security-setting changes.
4. Observe existing `contract`, `test`, `package`, and `security` CI jobs on the exact final commit, addressing actual failures without weakening gates.
5. Fetch/prune and prove main equals origin/main, clean tracked/untracked state, no task branch/worktree/stash leftovers. Remove only this task's validated scratch artifacts after extracting ledger decisions.
6. Hand off the actual outcome and limitations. A remaining failing/in-progress CI job means not fully ready; static fixtures never prove optimal gameplay.

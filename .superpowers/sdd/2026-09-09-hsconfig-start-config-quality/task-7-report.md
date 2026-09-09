# Task 7 implementation report

## Outcome

Task 7 is implemented in the approved main checkout. The normal bundled helper now follows the quality-start route by default, supports the closed `complete-research` phase, preserves exact controller receipts/results inside a minimal quality-only envelope, and obtains a read-only schema-2 route summary only after the controller phase returns. The original controller payload continues to determine the helper exit code.

`prepare_live_start(request)` now delegates to `prepare_quality_live_start(request)`. Legacy tests that intentionally exercise the prior schema-1 route call the existing `_prepare_legacy_live_start(request)` seam explicitly; no legacy persisted protocol was rewritten.

The new public diagnostic API is:

```python
quality_start_summary(*, run_root: Path) -> FrozenJsonDocument
```

It loads and validates the persisted session and bound research progress, derives the preserved artifact, finite acquisition/revision budgets, `runtime_write_state`, and one closed `next_action`, and performs no state transition or write. Schema-1 terminal summaries are returned with their original canonical bytes. Quality routing is selected from the validated session schema/version, not from the stored terminal summary schema.

## Files changed

- `src/hsconfig/live_start_controller.py`
  - Added the read-only quality route summary and closed state/action projection.
  - Cut the default `prepare_live_start` entry point over to quality preparation.
  - Preserved `_prepare_legacy_live_start` for explicit legacy callers.
- `src/hsconfig/resources/codex_skill_bundle.json`
  - Kept the exact nine-file inventory.
  - Updated bundled `SKILL.md`, `references/workflow.md`, `references/contract-compiler-checklist.md`, `references/card-behavior-policy.md`, `references/globalvalues-policy.md`, `references/guide-research-policy.md`, and `scripts/build_config.py`.
  - Left `references/visionai-surfaces.md` and `scripts/validate_package.py` byte-identical.
- `tests/test_optimized_skill_workflow.py`
  - Added the required closed helper tests, discovery serialization, minimal envelope/exit preservation, and one actual-controller helper-to-preview integration using only synthetic acquisition/candidate/reviewer inputs.
- `tests/test_quality_start_summary.py`
  - Added the parameterized closed action table, honest budget/write-state assertions, hash-free deck-label check, schema-1 byte preservation, and changed-progress rejection.
- `tests/test_external_skill_bundle.py`
  - Updated only the aggregate and three explicitly changed pinned policy hashes; inventory/equality/assertion logic is unchanged.
- `tests/test_live_start_controller.py`, `tests/test_codex_first_live_e2e.py`, `tests/test_live_start_preparation_failures.py`
  - Changed only intentional legacy-prepare calls to the explicit legacy seam (plus formatter line wrapping).

`src/hsconfig/external_skill_bundle.py` did not need a change.

## Bundle identity and instruction validation

Aggregate changed from `5a3bb29a895e06080a8ccff786789fe9d3de691cd76cad3167ed2d474b10d682` to `e4a10d53a60935549b22e1f21e8d9a34a0c84dfd4df0e5f61d34c98a14fbba20`.

The three changed policy pins are:

- `references/card-behavior-policy.md`: `c2457ac64a2601c9b27fa55aae344bf8f8e2132d4a93aa9bf8795f0b963be5b0` -> `db27f9e115b77d83713a3a54e5563dd3980510974b464f002953fc82b5b4aa3d`. Necessity: replace only the two directly contradictory normal-route three-candidate paragraphs while explicitly distinguishing schema-1 three-candidate, schema-2 single-candidate compatibility, and schema-3 quality.
- `references/globalvalues-policy.md`: `383d6da6bd90e6c160aa9843b55ae91d816a7eeb66a8fa8e99e0b390603ed0df` -> `32bac2c59998c206fdc5b67b38533e9ada33956aaea6af59e36054553767e183`. Necessity: require schema-3 changed-key justifications and preserve meaningful Mulligan-only intent without inventing GlobalValues changes.
- `references/guide-research-policy.md`: `7b8e838d8da370f5b5f32502db6aec367e190fe0b91d95944926ea7b6f0a5343` -> `45cb78ec1c2d5c3f0ce34272771d1df5716377416087aab3bc47886a8bb8f9bb`. Necessity: document the bounded quality acquisition handoff, untrusted source treatment, and no reset of reserved/spent queries.

The final instruction hashes are `SKILL.md` `4a0cb14f7a1f9ac7fc33481af1e9592ff400a1277ea9b9d8f9a94f01b2b2b6b7` and `references/workflow.md` `61e7875c5b22b591cbd146f80458e93b46752b09f373caa8de2632fc047819c3`. The independent reference evaluator first found that the complete-research handoff did not name the exact draft key/shape or clearly separate Codex search from controller fetches. After the narrow instruction correction, the repeated evaluator marked the normal route clean and usable. It confirmed same-run continuation, the exact `acquisition_request_sha256` draft, separate query/page budgets, preserved external partial URLs, correct lead/reviewer timing, and no apply authority. The later helper-only hardening changed the aggregate but did not change either evaluated instruction hash.

The final nine bundle members are:

| Path | Size | SHA-256 |
| --- | ---: | --- |
| `SKILL.md` | 10425 | `4a0cb14f7a1f9ac7fc33481af1e9592ff400a1277ea9b9d8f9a94f01b2b2b6b7` |
| `references/card-behavior-policy.md` | 12015 | `db27f9e115b77d83713a3a54e5563dd3980510974b464f002953fc82b5b4aa3d` |
| `references/contract-compiler-checklist.md` | 6176 | `3b1837573a8b4e4314c4d526673f2ccd0caaed13995ac45a445ba31c69b9ee6d` |
| `references/globalvalues-policy.md` | 6044 | `32bac2c59998c206fdc5b67b38533e9ada33956aaea6af59e36054553767e183` |
| `references/guide-research-policy.md` | 25413 | `45cb78ec1c2d5c3f0ce34272771d1df5716377416087aab3bc47886a8bb8f9bb` |
| `references/visionai-surfaces.md` | 2342 | `ed5c5b3f497188598f86a01ddde8cf9372644706bc0bf7cf12c1ab50adddace0` |
| `references/workflow.md` | 30530 | `61e7875c5b22b591cbd146f80458e93b46752b09f373caa8de2632fc047819c3` |
| `scripts/build_config.py` | 4822 | `1627ba883feca7fc25e8135051f93df48bb8d5a341e05e4c3b0c633f9665d18f` |
| `scripts/validate_package.py` | 260 | `833dfc822999b5105c45319dd805fd7fb1730c89e13150e70f154656854482d9` |

## TDD and verification evidence

Environment for every pytest command: `PYTHONDONTWRITEBYTECODE=1`; cache plugin disabled with `-p no:cacheprovider`.

### RED

```text
python -m pytest -q -p no:cacheprovider tests/test_optimized_skill_workflow.py -k 'complete_research or exact_single_candidate or closed_controller or duplicate_abbreviated'
4 failed, 12 passed, 10 deselected in 4.92s
```

The failures were the intended missing `complete-research` parser/dispatch surface and missing quality workflow requirements.

The first actual integration attempt exposed a fixture wiring error (`fixture 'quality_request' not found`; `1 error in 1.15s`). After the fixture adapter, it exposed an incorrect test assumption about the returned context location (`1 failed in 10.74s`). The test was corrected to load the controller-returned sealed `starter_context_path`; no production bypass was added.

The writing-skill reference scenario also had a real RED: the first evaluator found an underspecified complete-research draft/search-to-fetch handoff. Only that prose seam was corrected and re-evaluated as described above.

### GREEN

Required actual-default integration, run once:

```text
python -m pytest -q -p no:cacheprovider tests/test_optimized_skill_workflow.py::test_actual_default_helper_reaches_preview_with_synthetic_transport
1 passed in 83.08s
```

Final focused helper selection after the last helper hardening:

```text
python -m pytest -q -p no:cacheprovider tests/test_optimized_skill_workflow.py -k 'complete_research or exact_single_candidate or closed_controller or duplicate_abbreviated or quality_envelope or serializes_discovery or preserves_controller_failure_and_summary or review_helper_accepts_approved'
22 passed, 6 deselected in 6.61s
```

Summary and exact bundle/helper compilation:

```text
python -m pytest -q -p no:cacheprovider tests/test_quality_start_summary.py
8 passed in 1.02s

python -m pytest -q -p no:cacheprovider tests/test_external_skill_bundle.py -k 'embedded_bundle_is_exact_closed_nine_file_contract or bundle_decoder_compiles_both_python_helpers'
2 passed, 121 deselected in 0.64s
```

Genuinely affected representative legacy nodes:

```text
python -m pytest -q -p no:cacheprovider tests/test_live_start_controller.py::test_prepare_requires_only_deck_name_and_code_after_profile_enablement tests/test_codex_first_live_e2e.py::test_supported_non_thirty_resolvable_deck_reaches_preview_with_exact_coverage tests/test_live_start_preparation_failures.py::test_context_io_failure_after_session_creation_is_durable_bounded_failure
3 passed in 74.44s
```

Scoped lint and whitespace validation:

```text
python -m ruff check --no-cache src/hsconfig/live_start_controller.py tests/test_optimized_skill_workflow.py tests/test_quality_start_summary.py tests/test_external_skill_bundle.py tests/test_live_start_controller.py tests/test_codex_first_live_e2e.py tests/test_live_start_preparation_failures.py
All checks passed! (0.65s)

git -c core.autocrlf=false diff --check
PASS
```

No Task 6 long file or broad suite was rerun.

## Boundaries and concerns

- The preview integration uses the real default helper and actual quality controller/session transitions, but its card acquisition transport, candidate, and reviewer inputs are synthetic fixtures. It proves helper-to-`PREVIEW_READY` integration, schema-3 artifacts, and absence of runtime writes; it does not prove real web acquisition, installed-skill behavior, HearthRanger in-client behavior, gameplay quality, or optimality.
- No network acquisition, runtime apply, installed-skill/profile write, credential/provider use, branch/worktree creation, or push occurred.
- The helper adds no authority. A quality envelope preserves the original exact controller payload under `controller_result` and puts the read-only route projection under `quality_route_summary`; legacy output stays shape-compatible. Missing/invalid persisted quality state fails closed instead of being reported as success.
- The mechanically decoded temporary bundle directory was verified and removed after regeneration.

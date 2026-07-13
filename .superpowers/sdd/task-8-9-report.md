# Task 8 and Task 9 Focused Verification Report

## Status

Complete. Task 8 adds two end-to-end regression tests. Task 9 focused
verification passed. The plan and research package were already committed in
`1f97a3e` (`docs: plan contract spine semantic qualifier wave`).

## Changed Files

- `tests/test_shadowpriest_e2e.py`
  - Proves `ShadowPriest` remains `VALID_PACKAGE` while `SW_448` is not a
    Mulligan hold.
- `tests/test_universal_wild_no_block_matrix.py`
  - Adds a local prepare fixture helper and proves an unknown semantic state
    qualifier remains report-visible without blocking a valid package or
    changing the apply authority.

## Verification

- Research validation: PASS, 6/6 result files, 100.0% average coverage.
- `tests/test_preconfig_context_parity.py tests/test_guide_claim_bundle_parity.py tests/test_semantic_qualifiers.py tests/test_source_claim_conflicts.py`: PASS, 15 tests.
- `tests/test_surface_authority_split.py tests/test_source_contract_conformance.py tests/test_source_claim_quality_autonomy.py tests/test_apply_authority_boundary.py`: PASS, 51 tests.
- `tests/test_shadowpriest_e2e.py tests/test_shadowpriest_depth_e2e.py tests/test_universal_wild_no_block_matrix.py`: PASS, 20 tests.
- `python -m compileall -q src tests`: PASS.
- `git diff --check`: PASS.
- Policy scans: PASS. Active paths retain `Presume.json` and `Concede.json` as
  legacy/diagnostic surfaces and retain `reports/operator_summary.json` as the
  only normal apply authority.

## Self-Review

- The new tests use the normal `prepare` path only; they neither write runtime
  configuration nor add an apply authority.
- Darkbishop effect behavior remains covered by the existing emitted CardID
  assertions; the new regression independently rejects a `SW_448` hold row.
- The unknown qualifier fixture preserves `future_mechanic` in the generated
  guide-claim diagnostic bundle and verifies `VALID_PACKAGE` plus the existing
  `reports/operator_summary.json` authority.

## Concerns

- The task brief's `--skip-semantic-fetch` argument is not supported by the
  current `prepare` CLI, so the tests use the current normal CLI surface.
- The full repository test suite was intentionally not run: this was Task 9
  focused verification preparation, and all requested focused groups passed.

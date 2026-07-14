# Final Review Fix Report

## Status

DONE

## Summary

- Added closure-level `expected_runtime_surfaces` and `missing_runtime_surfaces` to source-to-runtime explainability rows.
- Changed operator summary surface filtering so empty/no-intent default-only rows no longer match every default-only surface.
- Removed the surface-detail fallback that substituted all risky cards when a specific default-only surface had no matching risky cards.
- Treated normalized `semantic_qualifiers.timing == "mulligan"` as explicit opening-hand mulligan evidence, alongside existing prose and role evidence.

## Tests

Red tests were added first for:

- producer-built baseline-only rows with no runtime surface intent;
- closure rows that distinguish expected/missing surface intent from emitted files;
- opening-hand semantic qualifier evidence without opening-hand prose.

Focused verification run after implementation:

```text
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_operator_summary.py tests/test_semantic_qualifiers.py tests/test_claim_kind_runtime_contract.py
137 passed in 0.75s

python -m pytest tests/test_source_contract_closure_wave.py tests/test_semantic_runtime_negative_boundaries.py tests/test_shadowpriest_e2e.py tests/test_shadowpriest_fresh_closure_proof.py
31 passed in 21.85s
```

## Scope Check

Changed only the requested source files, focused tests, and this SDD report. No replay parsing, HDT parsing, winrate validation, candidate promotion, post-run tuning, runtime writes, or docs/plan/research artifacts were added.

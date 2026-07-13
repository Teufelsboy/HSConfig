# Tasks 3-4 Report

## Status

Completed. Semantic qualifiers are normalized as explanatory claim metadata and qualify existing evidence gates without adding a claim kind, runtime surface, or apply authority. Qualifier-only start-of-game/deckbuilding effects now suppress unsupported mulligan keeps unless source text explicitly states opening-hand/mulligan intent.

## Changed files

- `src/hsconfig/source_semantic_qualifiers.py`
- `src/hsconfig/source_document_builder.py`
- `src/hsconfig/guide_claim_builder.py`
- `src/hsconfig/source_evidence_verifier.py`
- `src/hsconfig/source_document_model.py`
- `tests/test_semantic_qualifiers.py`

## Commit

- Tasks 3-4 implementation commit: this commit.

## Tests run

- `python -m pytest tests/test_semantic_qualifiers.py tests/test_source_claim_quality_autonomy.py tests/test_surface_authority_split.py tests/test_archetype_source_fixtures.py -q` - 67 passed.
- `python -m pytest tests/test_semantic_qualifiers.py tests/test_source_claim_quality_autonomy.py tests/test_archetype_source_fixtures.py -q` - 57 passed.
- `python -m compileall -q src tests` - passed.
- `git diff --check` - passed.

## Self-review

- Normalization drops empty qualifier values and preserves only recognized metadata keys.
- Qualifiers count as actionable specificity but do not change lowering authority.
- Darkbishop-style hero-power transforms remain eligible for card behavior configuration while mulligan lowering is blocked without explicit opening-hand evidence.
- Thin or unsupported mechanics remain warnings/report-visible; the suppression is not a package blocker.

## Concerns

- None.

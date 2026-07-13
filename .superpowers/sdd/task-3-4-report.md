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

## Review Finding Fix

### Changed files

- `src/hsconfig/source_semantic_qualifiers.py`
- `src/hsconfig/guide_claim_builder.py`
- `tests/test_semantic_qualifiers.py`
- `.superpowers/sdd/task-3-4-report.md`

### Commit

- Fix commit: this commit (`fix: derive qualifiers for static start effects`).

### Tests run

- `python -m pytest tests/test_semantic_qualifiers.py tests/test_source_claim_quality_autonomy.py tests/test_surface_authority_split.py tests/test_archetype_source_fixtures.py tests/test_guide_claim_builder.py tests/test_source_evidence_verifier.py -q` - 97 passed.
- `python -m compileall -q src tests` - passed.
- `git diff --check` - passed.

### Self-review

- Static claim normalization supplies existing static semantic families as card-role context, so Darkbishop-style text derives `timing=start_of_game`.
- Singular static `mechanic` and `mechanic_family` participate as normalized role hints, yielding `state_requirements` with `hero_power_transform`.
- The regression covers the public guide claim builder and asserts metadata only. It adds no claim kind, runtime surface, dependency, apply authority, or Mulligan keep.

# Task 3 Report: Add Source Document Model And Atomic Claim Builder

## Status

DONE

## Files Changed

- `src/hsconfig/source_document_model.py`
- `src/hsconfig/source_document_builder.py`
- `src/hsconfig/guide_claim_builder.py`
- `tests/test_source_document_builder.py`
- `tests/test_guide_claim_builder.py`
- `.superpowers/sdd/task-3-report.md`

No changes were required in `src/hsconfig/guide_source_builder.py`; the Task 3 integration point was isolated to `guide_claim_builder.py`.

## Tests Run

- `python -m pytest tests/test_source_document_builder.py -q`
  - Red outcome before implementation: failed during collection with `ModuleNotFoundError: No module named 'hsconfig.source_document_builder'`.
- `python -m pytest tests/test_guide_claim_builder.py::test_source_documents_are_integrated_before_static_semantic_backfill -q`
  - Red outcome before implementation: failed with `KeyError: 'claim_coverage_report'`.
- `python -m pytest tests/test_source_document_builder.py tests/test_guide_claim_builder.py -q`
  - Green outcome after implementation: `10 passed in 0.09s`.
- `python -m pytest tests/test_source_document_builder.py tests/test_guide_claim_builder.py tests/test_research_contract.py -q`
  - Targeted Task 3 outcome: `14 passed in 0.09s`.
- `git diff --check -- src/hsconfig/source_document_model.py src/hsconfig/source_document_builder.py src/hsconfig/guide_source_builder.py src/hsconfig/guide_claim_builder.py tests/test_source_document_builder.py tests/test_guide_claim_builder.py`
  - Outcome: passed; Git reported CRLF normalization warnings only.
- `python -m pytest -q`
  - Full-suite outcome before commit: `198 passed in 29.56s`.

## Commits Created

- `feat: build atomic source-backed guide claims` (final hash assigned by Git when this report is committed)

## Self-Review Notes

- Added explicit source document constants for supported atomic claim kinds and required source/claim keys.
- Added `build_source_document_bundle(...)` with stable source-backed claim IDs, `source_evidence_index`, per-card `claim_coverage_report`, empty Task 4-ready `claim_conflict_report`, and `unsupported_claims`.
- Unsupported claims now cover non-object claims, non-list claim payloads, unsupported claim kinds, missing required claim text/kind, non-card-specific claims, and card-scoped claims that reference cards outside the deck.
- Source validation records missing source keys in `source_evidence_index` while preserving legacy compatibility for partially populated source documents.
- `build_guide_claim_bundle(...)` now calls the source document builder before static semantic backfill, keeps source-backed claims first, preserves legacy `coverage`, and exposes `claim_coverage_report` plus `claim_conflict_report`.
- Existing runtime-lowering fields such as `runtime_block`, `runtime_value`, `condition`, and `conditions` are preserved for `card_behavior_router`.
- The unrelated untracked plan document under `docs/superpowers/plans/` was left untouched.

## Concerns

None.

---

## Task 3 Review Fix: Source Document Claim Validation

## Status

DONE

## Fix Commit

- `132b0ef69de61e8210d58bb081a885b3b3c35dca` (`fix: enforce source document claim validation`)

## Files Changed

- `src/hsconfig/source_document_builder.py`
- `tests/test_source_document_builder.py`
- `tests/test_guide_claim_builder.py`

## Review Findings Fixed

- Missing or blank `source_confidence` is now treated as `missing_claim_keys`; those claims are routed to `unsupported_claims` and are not promoted as `source_backed`.
- Documents missing any `REQUIRED_SOURCE_KEYS` now promote zero claims. Each affected claim is emitted as unsupported evidence with `reason="missing_source_keys"` and the exact `missing_source_keys`.
- `build_source_document_bundle(...)` now keeps its own `claim_coverage_report` source-only: cards without accepted source claims are `uncovered_low_confidence`. Static semantic coverage remains in `guide_claim_builder` only after static claim rows are appended.

## Regression Tests Added

- `test_missing_or_blank_source_confidence_is_not_promoted`
- `test_missing_source_keys_reject_all_claims_from_document`
- `test_source_document_coverage_is_source_only_without_static_backfill`
- Added guide-bundle coverage assertions proving `static_semantics_backfilled` is reported only after static semantic claim rows exist.

## Tests Run

- `python -m pytest tests/test_source_document_builder.py tests/test_guide_claim_builder.py -q`
  - Red before fix: `3 failed, 10 passed in 0.19s`
  - Green after fix: `13 passed in 0.07s`
- `python -m pytest tests/test_research_contract.py -q`
  - Green after fix: `4 passed in 0.06s`
- `git diff --check -- src/hsconfig/source_document_model.py src/hsconfig/source_document_builder.py src/hsconfig/guide_claim_builder.py tests/test_source_document_builder.py tests/test_guide_claim_builder.py`
  - Passed; Git reported CRLF normalization warnings only.

## Concerns

None.

# Task 5 Report: Suppress Misleading Card-Level Explainability Gaps

Status: DONE

## Scope

- Updated `src/hsconfig/source_to_runtime_explainability.py`.
- Updated `tests/test_source_to_runtime_explainability.py`.
- Kept claim-level rows, claim-level `first_missing_link`, and evidence-chain diagnostics unchanged.
- Did not change apply permission, source-strength gates, or runtime-write behavior.

## Implementation

- Added `_card_level_first_missing_link` with the required emitted-surface and missing-runtime-surface rule.
- Card aggregation now determines emitted and missing runtime files before deriving the card-level missing link.
- A card with emitted runtime files and no remaining expected runtime files now reports `first_missing_link: null`; the underlying claim still reports its original missing link.
- The card summary count and operator-facing row consume the resulting card-level field, so they no longer report the misleading card-level gap.

## TDD Evidence

1. Added `test_explainability_keeps_claim_gap_but_not_card_gap_when_runtime_is_emitted` for `NX2_019` with an emitted runtime claim and a `not_seen_by_builder` card-role claim.
2. RED: `python -m pytest tests/test_source_to_runtime_explainability.py -q` failed because the card-level value was `builder_or_router` instead of `None`.
3. GREEN: implemented the narrow aggregation helper and updated pre-existing aggregate expectations that intentionally covered the prior behavior.

## Verification

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_source_to_runtime_explainability.py tests/test_contract_doctor.py tests/test_contract_preflight.py -q
```

Result: `69 passed in 10.08s`.

`git diff --check` passed before commit.

## Concerns

None. This change is diagnostic-only; no runtime package generation, apply permission, source-strength gate, or runtime-write path was modified.

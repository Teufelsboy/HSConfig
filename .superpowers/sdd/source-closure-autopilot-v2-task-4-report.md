## Task 4 Report: Lock Darkbishop And Static Semantics Runtime Boundaries

Status: DONE

### Scope Completed

- Added a focused regression test proving that Darkbishop Benedictus' static hero-power transform semantics can lower to CardID/effect behavior.
- Proved the same static effect claim cannot lower to the Mulligan surface.
- Proved an independent guide-backed keep claim can still lower to Mulligan without creating a CardID behavior row.
- No source implementation was changed because the existing boundary logic already satisfied the new contract.

### Test Evidence

1. Precision test:
   `python -m pytest tests/test_claim_kind_runtime_contract.py::test_darkbishop_static_effect_and_guide_mulligan_keep_are_independent_claims -q`
   Result: `1 passed in 0.32s`
2. Runtime contract and router suite:
   `python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_card_behavior_router.py -q`
   Result: `88 passed in 0.45s`

### Constraints Preserved

- No Mulligan keep is emitted for `hero_power_transform`.
- No CardID row is emitted for `mulligan_keep`.
- Darkbishop's start-of-game effect remains modeled as an effect/runtime behavior, not an opening-hand keep.
- The change is test-only and keeps the runtime surface model narrow.

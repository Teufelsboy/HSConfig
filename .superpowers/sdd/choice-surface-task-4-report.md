# Task 4 Report: Prepare-Level Choice Surface Proof

## Status

DONE_WITH_CONCERNS

## Scope Completed

- Strengthened `tests/test_prepare_cli.py` to assert that `prepare` writes a concrete per-card `OnDiscoverCardBonus` row for the resolved Discover identity-linked claim.
- Added a new prepare-level Choose One proof test that checks:
  - the resolved claim is routed to `OnChooseOneCardBonus`,
  - no claims are suppressed,
  - the option resolution is recorded,
  - the generated per-card `CHOOSE_CARD.json` contains the expected bonus row.

## Verification

Ran:

```powershell
python -m pytest tests/test_prepare_cli.py::test_prepare_routes_option_claim_with_identity_links tests/test_prepare_cli.py::test_prepare_routes_choose_one_claim_with_identity_links -q
python -m pytest tests/test_compile_cardid.py tests/test_condition_format.py tests/test_prepare_cli.py -q
```

Result:

- Focused prepare tests: `2 passed`
- Related compile and CLI suite: `44 passed`

## Commit

- `ba86f9a` - `test: prove choice surfaces in prepare output`

## Concerns

- The Discover prepare output in this branch still includes an additional generic fallback row alongside the resolved option-specific row, so the proof assertion had to check membership rather than exact single-row equality.
- The task brief provided exact assertion text, but the current branch behavior is broader than that exact list shape.

## Fix Report

- Root cause: the router emitted a generic `mechanic_usage` discover row even when the same card already had a resolved `discover_choice` row in the same pass.
- Fix: `src/hsconfig/card_behavior_surface_router.py` now precomputes resolved `discover_choice` cards and suppresses later generic discover/dredge fallback rows for those cards with reason `covered_by_resolved_choice_surface`.
- Regression coverage:
  - Added a router-level test that proves the resolved choice row is kept and the generic discover fallback is suppressed.
  - Tightened the prepare-level Discover proof back to exact single-row equality for `OnDiscoverCardBonus`.

## Verification

Ran:

```powershell
python -m pytest tests/test_card_behavior_router.py -q
python -m pytest tests/test_prepare_cli.py::test_prepare_routes_option_claim_with_identity_links tests/test_prepare_cli.py::test_prepare_routes_choose_one_claim_with_identity_links -q
python -m pytest tests/test_compile_cardid.py tests/test_condition_format.py tests/test_prepare_cli.py -q
```

Result:

- Router tests: `25 passed`
- Prepare target tests: `2 passed`
- Compile/condition/prepare suite: `44 passed`
## Task 4 Regression Coverage Addendum

### Fix
- Added a direct surface-router regression test in `tests/test_card_behavior_router.py`:
  - `test_standalone_discover_mechanic_claim_routes_to_discover_surface`
- The test calls `route_card_behavior_surfaces` directly with a single source-backed/static-semantics
  `mechanic_usage` discover claim (`claim_readiness: source_backed_static_semantics`) and no
  discover-choice/identity context.
- It verifies exact routing behavior: one emitted row on `OnDiscoverCardBonus`, wildcard `condition`,
  `roles == ["discover"]`, and no suppressed claims.

### Test
- Command: `python -m pytest tests/test_card_behavior_router.py -q`
- Result: `26 passed`

## Task 4 Partial Resolution Edge Case

### Fix
- Adjusted `src/hsconfig/card_behavior_surface_router.py` so `_resolved_choice_cards()` now records resolved cards per row instead of requiring every card on a `discover_choice` claim to resolve.
- This preserves the existing suppression of the unresolved `discover_choice` claim itself while still letting later generic discover fallback logic suppress the resolved subset only.

### Regression Test
- Added `test_partial_discover_choice_resolution_suppresses_only_resolved_cards` to `tests/test_card_behavior_router.py`.
- The test covers a two-card `discover_choice` claim where only `CARD_RESOLVED` links to `OPTION_ALPHA`, then a later generic discover claim spanning both cards.
- Expected outcome verified:
  - the unresolved option claim remains suppressed,
  - `CARD_RESOLVED` is covered by the resolved choice surface,
  - `CARD_UNRESOLVED` still emits the generic discover fallback row,
  - `option_resolution` records one resolved row and one unresolved row.

### Verification
- Command: `python -m pytest tests/test_card_behavior_router.py -q`
- Result: `27 passed`

# Task 4 Report: Policy Mulligan Source Veto

## RED

Command:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_autonomous_mulligan_policy.py `
  tests/test_boarlock_fracking_source_decision.py `
  tests/test_kingslayer_quick_pick_source_decision.py `
  tests/test_multideck_source_backed_e2e.py
```

Result before production changes: `1 failed, 25 passed`.

The named E2E regression failed because the policy still emitted a hold for
Boarlock `WW_092`.

The source-suppression visibility assertion was also verified independently:
without the preservation row, the prepared Boarlock report lacked
`claim_not_runtime_lowerable`.

## Implementation

- Added one `policy_veto_card_ids` projection in `mulligan_plan.py`.
- Projected vetoes from suppressed exact Mulligan intent, documented exact-card
  Mulligan stop conditions, `sideboard_owner`, and non-hand start-of-game roles
  without independent exact Mulligan authority.
- Passed stable reasons through `excluded_card_reasons`.
- Preserved the original non-lowerable source-gap reason alongside the
  `source_veto` policy row.
- Kept ordinary exact-deck surface rejects eligible for safe policy fallback.
- Kept accepted and condition-suppressed source discards excluded under their
  existing `excluded_source_mulligan_intent` contract.
- Added no deck-name or CardID special case to the autonomous policy.

## GREEN

Required Task-4 suite:

```text
67 passed in 25.87s
```

Additional compatibility suite:

```text
40 passed in 0.33s
```

The additional suite covers the complete existing Mulligan-plan and
source-claim-gap report tests.

## Commit

Local commit message:

```text
fix: honor explicit source gaps in mulligan policy
```

The final commit hash is reported in the task handoff. Nothing is pushed.

## Self-Review

- `WW_092`, `DEEP_014`, and `TOY_330` cannot re-enter the concrete hold set or
  through the wildcard discard rule.
- The required reasons are visible as
  `explicit_source_gap_requires_resolution` and
  `sideboard_owner_not_curve_anchor`.
- The original `claim_not_runtime_lowerable` source-gap reason remains visible
  for Boarlock and Kingslayer.
- The safe lowest-curve fallback still selects an unconflicted card.
- `git diff --check` is required immediately before staging.

## Concerns

- Documented exact-card stop conditions are projected from the existing
  `known_coverage_limits` `first_missing_chain` schema. A future schema change
  must update that normalizer and its E2E regression together.
- Runtime, HSTuner, replay, and desktop behavior were not exercised because
  they are explicitly outside Task 4.

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

- Runtime, HSTuner, replay, and desktop behavior were not exercised because
  they are explicitly outside Task 4.

## Specification Review Fix Round 1

The initial implementation failed specification review for two reasons:

1. It allowed exact-card lifecycle/surface rejections to become policy holds.
2. It read the diagnostic fixture matrix from production Mulligan code and
   synthesized a provenance-free source-gap row.

### Fix-Round RED

Focused command:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_mulligan_plan.py::test_policy_vetoes_exact_card_from_lifecycle_rejected_guide_claim `
  tests/test_mulligan_plan.py::test_non_card_specific_lifecycle_rejection_keeps_safe_policy_fallback `
  tests/test_multideck_source_backed_e2e.py::test_policy_mulligan_honors_named_source_and_role_vetoes
```

Result before the fix-round production changes: `2 failed, 1 passed`.

- The exact rejected `TOY_381` claim became a policy hold.
- Boarlock lacked a real `claim_not_runtime_lowerable` row with Claim-ID and
  source provenance.
- The card-free rejection control retained its safe fallback.

### Fix-Round Implementation

- Removed `fixture_row_for(deck_name)` and all fixture-matrix parsing from the
  production Mulligan path.
- Removed the synthetic `documented_source_gap` row with empty claim IDs.
- Passed the current normalized `initial_lifecycle_rows` explicitly from
  `package_builder` into `build_mulligan_plan`.
- Projected the real report-only Mulligan claims, including their Claim-ID,
  source URL, source references, acquisition provenance, readiness, and trust
  ceiling.
- Made every exact-card suppressed Mulligan claim a policy veto, including
  surface-gate rejections.
- Kept card-free lifecycle/surface rejections from manufacturing a veto card,
  so an unrelated safe curve fallback remains available.

### Fix-Round GREEN

Required Task-4 suite:

```text
67 passed in 26.52s
```

Complete Mulligan-plan and source-gap compatibility suite:

```text
41 passed in 0.36s
```

The fix round is committed separately from the initial Task-4 commit. Its final
local commit hash is reported in the task handoff; nothing is pushed.

### Remaining Risk

The production policy now depends only on the current normalized lifecycle
contract. A future lifecycle schema change must preserve the `claim` payload,
`claim_id`, `claim_kind`, and `runtime_eligibility` fields or update the
projection and its contract tests together.

## Quality Review Fix Round 2

The second review found three loss-of-provenance cases in the report-only
Mulligan lifecycle projection:

1. An ID-less source claim received a canonical lifecycle `claim_id`, but its
   `source_claim_ids` remained empty.
2. A rejected exact-card claim containing multiple cards emitted only the first
   card.
3. A rejected `mulligan_discard` claim was projected with action `none`.

### Fix-Round RED

Focused command:

```powershell
python -m pytest tests/test_mulligan_plan.py -q -k `
  "generated_lifecycle_id_as_source_claim_id or `
  report_only_multicard_mulligan_claim or `
  report_only_mulligan_discard"
```

Result before the production fix: `3 failed, 29 deselected`.

Each failure reproduced one review finding: empty `source_claim_ids`, a missing
second card row, and `none` instead of `discard`.

### Fix-Round Implementation

- Made `_source_claim_ids` use the same canonical `lifecycle_claim_id` helper as
  the top-level projected `claim_id` when no non-empty source-ID list exists.
- Added one lifecycle-suppression projector that emits one row per exact card.
- Normalized lifecycle actions as `mulligan_keep => hold` and
  `mulligan_discard => discard`.
- Preserved the real source URL and source type on every emitted lifecycle row.
- Left policy-veto derivation and the three named deck/card cases unchanged.

### Fix-Round GREEN

Focused regressions:

```text
3 passed, 29 deselected in 0.25s
```

The prior 67-test Task-4 suite now contains the three new regressions:

```text
70 passed in 27.72s
```

Relevant lifecycle and runtime-contract tests:

```text
143 passed in 0.48s
```

`git diff --check` completed without errors.

### Remaining Risk

This round changes the normalized lifecycle projection. Direct non-lifecycle
claims rejected only by the lower-level Mulligan gate retain their existing
single-card diagnostic projection; package preparation normally supplies the
lifecycle rows covered by these regressions.

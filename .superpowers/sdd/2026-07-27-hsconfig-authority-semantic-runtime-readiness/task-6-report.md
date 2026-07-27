# Task 6 implementation report

Status: DONE

## Outcome

- `reciprocal_hero_burn` remains report-only with the explicit suppression
  reason `reciprocal_burn_report_only`. This applies to both `GVG_009` and
  `VAC_419`; neither can emit a physical card behavior block.
- Existing summon-engine routing emits one `OnBoardBonus` row per persistent
  runtime owner. Regression coverage verifies the deduplicated row and merged
  claim provenance for `TOY_518` and `WON_065`.
- Existing linked ownership keeps `SW_448` as the source and emits exactly one
  `BeforeUseHeroPowerBonus` on `EX1_625t` with
  `link_kind="hero_power_transform"`. The `SW_448` file receives no hero-power
  block.
- The compiler's existing runtime-row canonicalization is covered at the
  physical output boundary using `(runtime_card_id, behavior_block, condition,
  value)` duplicates.

## TDD evidence

RED:

- Focused router/compiler/configure test run initially produced two expected
  failures: `GVG_009` and `VAC_419` were physically withheld already, but their
  reason was the generic `semantic_surface_not_expressible` instead of the
  required `reciprocal_burn_report_only`.

Fix:

- The router now retains the computed semantic intent while applying the
  existing semantic runtime gate. Only the `reciprocal_hero_burn` intent maps a
  denied row to `reciprocal_burn_report_only`; no card ID or deck-specific
  branch was added.

GREEN:

- Focused Task-6 semantic/router/compiler/configure set: `4 passed`.
- Prescribed suite:

  `tests/test_card_behavior_router.py tests/test_compile_cardid.py`
  `tests/test_claim_kind_runtime_contract.py`
  `tests/test_configure_online_source.py`
  `tests/test_config_quality_contract.py`
  `tests/test_strict_package_validation.py`

  Result: `341 passed in 67.41s`.
- Ruff on all modified Python files: passed.
- `git diff --check`: passed.

## Files changed

- `src/hsconfig/card_behavior_surface_router.py`
- `tests/test_card_behavior_router.py`
- `tests/test_compile_cardid.py`
- `tests/test_configure_online_source.py`

`card_intent_taxonomy.py`, `runtime_entity_owner.py`, and `compile_cardid.py`
needed no production change: their intent recognition, linked-owner routing,
and runtime-key canonicalization already satisfied the Task-6 contract. Tests
now assert those existing boundaries directly.

## Runtime boundary and residual risk

No runtime write, HSTuner invocation, Desktop/runtime access, branch creation,
or push occurred. The result is static/package-level evidence only; live game
behavior was intentionally not claimed.

# Task 5 Report: ShadowPriest Darkbishop Regression Closure

## Result

Closed the Darkbishop Benedictus (`SW_448`) regression boundary in tests and fixtures:

- `SW_448` remains a `hero_power_transform` claim for Shadowform / Mind Spike explainability.
- `SW_448` is explicitly marked `opening_hand_relevant: false`.
- `SW_448` is not allowed to appear in concrete `Mulligan.json` opening-hand keep output unless a future source supplies explicit mulligan evidence.
- No production code change was required.

## Changes

- Strengthened `tests/test_shadowpriest_depth_e2e.py` with fixture metadata assertions for `SW_448`.
- Strengthened the runtime E2E assertion so the full generated `Mulligan.json` payload must not mention `SW_448`.
- Added `card_rows` closure checks for `SW_448` in `source_to_runtime_explainability.json`.
- Added explicit `card_ids`, `opening_hand_relevant`, and `source_type` metadata to the ShadowPriest Darkbishop claims in:
  - `tests/fixtures/shadowpriest_guide_sources.json`
  - `tests/fixtures/source_documents_shadowpriest_strong.json`

## Red Evidence

Command:

```text
python -m pytest tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_darkbishop_fixtures_mark_effect_as_non_opening_hand_claim -q
```

Observed failure before fixture edits:

```text
FAILED tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_darkbishop_fixtures_mark_effect_as_non_opening_hand_claim
AssertionError: assert {None} == {'public_guide'}
1 failed in 0.65s
```

This proved the new test caught the missing explicit source metadata for the Darkbishop claim.

## Green Evidence

Narrow regression:

```text
python -m pytest tests/test_shadowpriest_depth_e2e.py::test_shadowpriest_darkbishop_fixtures_mark_effect_as_non_opening_hand_claim -q
1 passed in 0.37s
```

Required ShadowPriest E2E file:

```text
python -m pytest tests/test_shadowpriest_depth_e2e.py -q
6 passed in 29.15s
```

Directly relevant fixture/source checks:

```text
python -m pytest tests/test_archetype_source_fixtures.py tests/test_claim_kind_runtime_contract.py::test_hero_power_transform_is_strong_static_but_not_opening_hand_relevant tests/test_claim_kind_runtime_contract.py::test_source_family_card_text_hero_power_transform_promotes_as_official_static_claim tests/test_prepare_cli.py::test_prepare_writes_source_gap_and_promotion_reports tests/test_prepare_cli.py::test_prepare_writes_source_contract_audit_and_operator_summary_pointer -q
45 passed in 12.55s
```

## Concerns

- `tests/test_source_to_runtime_explainability.py` was already modified in the worktree and is outside Task 5 ownership scope. It was not inspected, changed, or staged.
- Git reports line-ending normalization warnings for the touched files on diff commands; no whitespace errors were observed in the task diff.

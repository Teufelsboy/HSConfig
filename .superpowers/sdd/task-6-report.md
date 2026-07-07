# Task 6 Report: Mulligan Selector Depth

## Status

DONE

## Changed Files

- `src/hsconfig/mulligan_selector.py`
- `src/hsconfig/mulligan_plan.py`
- `src/hsconfig/compile_mulligan.py`
- `src/hsconfig/validate_package.py`
- `src/hsconfig/source_document_builder.py`
- `tests/test_mulligan_plan.py`
- `tests/test_compile_mulligan.py`
- `tests/test_validate_package.py`
- `tests/test_source_document_builder.py`
- `.superpowers/sdd/task-6-report.md`

## Tests And Outcomes

RED:

- `python -m pytest tests/test_compile_mulligan.py::test_compile_mulligan_emits_drop_and_plus_selectors_in_plan_order tests/test_compile_mulligan.py::test_compile_mulligan_blocks_lone_wildcard_discard -q`
  - Outcome before implementation: 1 failed, 1 passed. Failure was the expected missing selector emission; plan selector rows compiled to no Mulligan runtime rows.
- `python -m pytest tests/test_mulligan_plan.py::test_mulligan_plan_preserves_source_claim_selector_depth tests/test_mulligan_plan.py::test_mulligan_plan_suppresses_unsupported_selectors tests/test_validate_package.py::test_validate_package_rejects_mulligan_wildcard_discard_before_hold tests/test_validate_package.py::test_validate_package_rejects_unsupported_mulligan_selector -q`
  - Outcome before implementation: 4 failed. Failures covered missing selector fields, unsupported selector suppression, wildcard discard ordering, and unsupported selector validation.
- `python -m pytest tests/test_source_document_builder.py::test_source_document_builder_preserves_mulligan_selectors -q`
  - Outcome before source-document pass-through: 1 failed. Failure showed source-document normalization stripped `selector_kind` and `selector`.

GREEN:

- `python -m pytest tests/test_compile_mulligan.py::test_compile_mulligan_emits_drop_and_plus_selectors_in_plan_order tests/test_compile_mulligan.py::test_compile_mulligan_blocks_lone_wildcard_discard -q`
  - Outcome: 2 passed.
- `python -m pytest tests/test_mulligan_plan.py::test_mulligan_plan_preserves_source_claim_selector_depth tests/test_mulligan_plan.py::test_mulligan_plan_suppresses_unsupported_selectors tests/test_validate_package.py::test_validate_package_rejects_mulligan_wildcard_discard_before_hold tests/test_validate_package.py::test_validate_package_rejects_unsupported_mulligan_selector -q`
  - Outcome: 4 passed.
- `python -m pytest tests/test_mulligan_plan.py tests/test_compile_mulligan.py tests/test_validate_package.py -q`
  - Outcome: 30 passed.
- `python -m pytest tests/test_mulligan_plan.py tests/test_compile_mulligan.py tests/test_validate_package.py tests/test_source_document_builder.py -q`
  - Outcome: 40 passed.
- `python -m pytest -q`
  - Outcome: 219 passed.
- `git diff --check`
  - Outcome: exit 0. Git printed CRLF conversion warnings for touched files only.

## Implementation Summary

- Added `normalize_mulligan_selector(rule)` for documented Mulligan selector kinds: `card`, `card_list`, `drop_n`, `plus_combo`, and `wildcard`.
- Updated Mulligan planning to preserve explicit selector fields, emit selector metadata for card-only and fallback rules, suppress unsupported selectors, and append wildcard discard only after a non-wildcard hold exists.
- Updated Mulligan compilation to emit normalized selector text in runtime `mulligan` rows while preserving plan order and blocking lone wildcard discard rules.
- Updated package validation to reject unsupported Mulligan selectors and wildcard discard rows that appear before any non-wildcard hold.
- Preserved source-document `selector_kind` and `selector` fields so source-backed guide claims can reach the Mulligan planner.

## Commits

- Task 6 implementation commit: `feat: support documented mulligan selectors`
- Final commit hash is reported in the controller final response because this report is included in the same commit.

## Self-Review

- Scope stayed focused on Mulligan selector depth. No CardID, Combo, GlobalValues, runtime-apply, replay, or tuning modules were changed.
- Runtime JSON rows remain official shape only: `comment`, `mulligan`, `condition`, and `value`.
- The planner retains the existing `card` field for compatibility with readiness/reporting while adding selector-level fields for new depth.
- Unsupported selector handling is conservative: unsupported planner selectors are suppressed; unsupported runtime selectors fail validation.
- Existing operator status gates remain covered by the full test suite.

## Concerns

- None.

## Review Fix: Selector Identity And Readiness Coverage

Status: DONE

Changed files:

- `src/hsconfig/mulligan_selector.py`
- `src/hsconfig/mulligan_plan.py`
- `src/hsconfig/config_readiness.py`
- `tests/test_mulligan_plan.py`
- `tests/test_config_readiness.py`
- `.superpowers/sdd/task-6-report.md`

RED:

- `python -m pytest tests/test_mulligan_plan.py::test_mulligan_plan_preserves_source_claim_selector_depth tests/test_mulligan_plan.py::test_mulligan_plan_suppresses_selector_cards_not_in_claim_before_runtime tests/test_config_readiness.py::test_multi_card_mulligan_selectors_credit_every_selector_card -q`
  - Outcome before implementation: 3 failed.
  - Failures covered missing `selector_cards`, off-deck selector emission, and readiness crediting only `row["card"]`.

GREEN:

- `python -m pytest tests/test_mulligan_plan.py::test_mulligan_plan_preserves_source_claim_selector_depth tests/test_mulligan_plan.py::test_mulligan_plan_suppresses_selector_cards_not_in_claim_before_runtime tests/test_config_readiness.py::test_multi_card_mulligan_selectors_credit_every_selector_card -q`
  - Outcome: 3 passed.
- `python -m pytest tests/test_mulligan_plan.py tests/test_config_readiness.py tests/test_compile_mulligan.py tests/test_validate_package.py -q`
  - Outcome: 42 passed.
- `python -m pytest -q`
  - Outcome: 221 passed.

Implementation summary:

- `normalize_mulligan_selector` now extracts selector card IDs for `card`, `card_list`, and `plus_combo`.
- `build_mulligan_plan` suppresses explicit selectors whose selector cards are not a subset of the claim's `cards`, using `selector_cards_not_in_claim`.
- Mulligan plan rows now carry `selector_cards` for selector-backed rows.
- Config readiness now uses `selector_cards` when present so every card in a multi-card Mulligan selector receives the `Mulligan.json` runtime surface.
- `source_document_builder.py`, `compile_mulligan.py`, and `validate_package.py` were not changed for this review fix.

Concerns:

- None.

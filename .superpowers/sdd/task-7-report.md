# Task 7 Report: Claim-Level CardID Behavior Routing

## Status

DONE

## Changed Files

- `src/hsconfig/card_behavior_surface_router.py`
- `src/hsconfig/card_behavior_router.py`
- `src/hsconfig/cli.py`
- `tests/test_card_behavior_router.py`
- `tests/test_compile_cardid.py`
- `tests/test_prepare_cli.py`
- `.superpowers/sdd/task-7-report.md`

## Tests And Outcomes

RED:

- `python -m pytest tests/test_card_behavior_router.py::test_card_behavior_router_routes_specific_runtime_blocks -q`
  - Outcome before implementation: 1 passed. The exact brief sample was already covered by the existing explicit `runtime_block` behavior.
- `python -m pytest tests/test_card_behavior_router.py::test_card_behavior_surface_router_routes_claim_kinds_in_input_order tests/test_card_behavior_router.py::test_card_behavior_surface_router_suppresses_unresolved_option_identity tests/test_card_behavior_router.py::test_card_behavior_router_preserves_claim_row_order_across_cards -q`
  - Outcome before implementation: 3 failed. Failures covered the missing `card_behavior_surface_router` module and sorted CardID row output instead of claim-order output.
- `python -m pytest tests/test_prepare_cli.py::test_prepare_source_posture_drives_globalvalues_authority_matrix -q`
  - Outcome before implementation: 1 failed. Failure was the expected missing `reports/card_behavior_suppression_report.json` artifact.

GREEN:

- `python -m pytest tests/test_card_behavior_router.py::test_card_behavior_surface_router_routes_claim_kinds_in_input_order tests/test_card_behavior_router.py::test_card_behavior_surface_router_suppresses_unresolved_option_identity tests/test_card_behavior_router.py::test_card_behavior_router_preserves_claim_row_order_across_cards -q`
  - Outcome: 3 passed.
- `python -m pytest tests/test_prepare_cli.py::test_prepare_source_posture_drives_globalvalues_authority_matrix -q`
  - Outcome: 1 passed.
- `python -m pytest tests/test_compile_cardid.py::test_compile_cardid_preserves_explicit_behavior_row_order_with_same_block -q`
  - Outcome: 1 passed.
- `python -m pytest tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_prepare_cli.py -q`
  - Outcome: 33 passed.
- `python -m pytest -q`
  - Outcome: 226 passed.
- `python -m compileall -q src tests`
  - Outcome: exit 0.
- `git diff --check`
  - Outcome: exit 0. Git printed CRLF conversion warnings for touched files only.

## Implementation Summary

- Added `route_card_behavior_surfaces(claims, identity_links=None)` with `rows`, `suppressed`, and `option_resolution` output keys.
- Added documented claim-kind block routing for `in_hand_value`, `on_board_value`, `play_timing`, `targeting_rule`, `hero_power_use`, `attack_posture`, `discover_choice`, and `choose_one_choice`.
- Preserved strict explicit block validation: a supplied `runtime_block` wins only when present in `CARD_BEHAVIOR_BLOCKS`; unsupported blocks remain suppressed.
- Added conservative option identity suppression for choice claims when supplied identity links do not resolve the requested option card.
- Kept `route_card_behavior_claims` as the compatibility wrapper and preserved `card_rows` while returning `rows` in claim order.
- Added the `card_behavior_suppression_report.json` sidecar report from `card_behavior_plan["suppressed"]`.
- Added compiler coverage proving explicit behavior rows retain source order within a runtime block.

## Commits

- Task 7 implementation commit: `feat: route guide claims to CardID behavior blocks`
- Final commit hash is reported in the controller final response because this report is included in the same commit.

## Self-Review

- Scope stayed within Task 7 files plus this report. Mulligan, Combo, and GlobalValues implementation paths were not changed.
- Runtime row shape remains compatible with existing CardID validation; provenance and suppression data stay in plan/report sidecars.
- `card_behavior_router.py` remains backward compatible for existing callers while the new module owns claim-level surface routing.
- The new suppression report is report-only and does not affect package runtime files.
- Targeted tests and the full suite passed after implementation.
- A subagent review was not available in this environment, so review was performed manually against the diff, task brief, and full test output.

## Concerns

- None.

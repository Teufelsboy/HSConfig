DONE

Status:
- Task 3 implementation is complete.
- Code commit: `ab7570f` (`fix: keep strong promotion evidence honest`)

Changed files:
- `src/hsconfig/operator_summary.py`
- `src/hsconfig/strong_promotion_report.py`
- `tests/test_operator_summary.py`
- `tests/test_strong_fixture_closure.py`
- `.superpowers/sdd/task-3-report.md`

Red evidence:
- `python -m pytest tests/test_operator_summary.py::test_policy_backed_package_is_load_safe_but_not_source_backed_strong tests/test_operator_summary.py::test_default_only_surface_blocks_strong_promotion_but_not_load_safe_apply -q`
- Result before implementation: `2 failed`
- Failure reason: both policy-backed and default-only valid packages were promoted to `SOURCE_BACKED_STRONG`.
- `python -m pytest tests/test_strong_fixture_closure.py::test_core_source_backed_fixture_stage_requires_source_backed_strong -q`
- Result before report implementation: `9 failed, 2 skipped`
- Failure reason: `strong_promotion_report.json` did not expose `static_contract_status`, `runtime_lowering_status`, or `first_missing_source_action`.

Green evidence:
- `python -m pytest tests/test_operator_summary.py::test_policy_backed_package_is_load_safe_but_not_source_backed_strong tests/test_operator_summary.py::test_default_only_surface_blocks_strong_promotion_but_not_load_safe_apply tests/test_strong_fixture_closure.py::test_core_source_backed_fixture_stage_requires_source_backed_strong -q`
- Result: `11 passed, 2 skipped`
- `python -m pytest tests/test_operator_summary.py tests/test_strong_fixture_closure.py -q`
- Result: `88 passed, 2 skipped`
- `python -m pytest tests/test_strong_promotion_report.py -q`
- Result: `9 passed`
- `git diff --check`
- Result: passed; Git printed CRLF normalization warnings for the four touched code/test files only.

Implementation notes:
- `SOURCE_BACKED_STRONG` now requires valid technical status plus no explicit default-only runtime surface evidence and no policy-only runtime evidence.
- `runtime_apply_allowed` remains tied to the technical apply contract, so weaker valid packages still stay load-safe.
- Policy fallback rows do not prove strong promotion. Coexisting policy fallback does not demote an otherwise source-backed fixture when another source-backed runtime surface already supports the package; this keeps the existing core fixture closure contract green.
- `strong_promotion_report` now emits `static_contract_status`, `runtime_lowering_status`, and `first_missing_source_action`.

Concerns:
- The plan listed additional blocker code names for snippet-only, missing runtime source claim, and static-not-observed cases. This Task 3 patch produces the policy/default blocker codes covered by the new regressions and maps the other code names in `strong_promotion_report` if upstream reports provide them, but it does not add new upstream detectors for those cases.

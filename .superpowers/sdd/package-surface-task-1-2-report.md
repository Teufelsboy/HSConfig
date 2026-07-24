# Package Surface Intent Preflight Receipt

## Scope

Implemented Tasks 1-2 of the HSConfig Package Surface Intent Preflight Receipt plan.
The change is limited to package-mode contract-preflight diagnostics. It does not
add runtime writes, replay or tuning logic, gameplay heuristics, card sequencing,
or a new apply authority.

## RED Evidence

Command:

```text
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_package_mode_aggregates_runtime_and_quality tests/test_contract_preflight.py::test_contract_preflight_package_mode_surfaces_missing_surface_intent_without_gate tests/test_contract_preflight.py::test_contract_preflight_cli_package_fallback_preserves_package_contract_schema -q
```

Result before implementation:

```text
FFF                                                                      [100%]
3 failed in 8.08s
```

All three failures were expected `KeyError: 'surface_intent_status'` failures,
demonstrating that the new tests exercised the missing package-contract schema.

## GREEN Evidence

Focused command:

```text
python -m pytest tests/test_contract_preflight.py::test_contract_preflight_package_mode_aggregates_runtime_and_quality tests/test_contract_preflight.py::test_contract_preflight_package_mode_surfaces_missing_surface_intent_without_gate tests/test_contract_preflight.py::test_contract_preflight_cli_package_fallback_preserves_package_contract_schema -q
```

Result:

```text
...                                                                      [100%]
3 passed in 0.55s
```

Broader command:

```text
python -m pytest tests/test_contract_preflight.py tests/test_config_quality_contract.py -q
```

Result:

```text
........................................................................ [ 92%]
......                                                                   [100%]
78 passed in 16.05s
```

## Changed Files

- `tests/test_contract_preflight.py`
  - Added the clean-package `surface_intent.json` fixture.
  - Added clean projection assertions.
  - Added missing-receipt non-gate coverage.
  - Added CLI fallback schema coverage.
- `src/hsconfig/contract_preflight.py`
  - Added the six `surface_intent_*` package-contract fields.
  - Added compact projection of `surface_intent_projection`.
  - Added missing-package defaults and normal package population.
  - Kept surface-intent diagnostics out of `failures`.
- `src/hsconfig/commands/contract_preflight.py`
  - Added the six fields to the exception fallback package-contract schema.
- `.superpowers/sdd/package-surface-task-1-2-report.md`
  - Added this implementation report.

## Self-Review

- Receipt authority remains `diagnostic_only`.
- `apply_blocking` remains `False`.
- `runtime_write_performed` remains `False`.
- `source_status_apply_blocking` remains `False`.
- Missing or attention-level surface intent does not affect `package_contract_current`.
- `reports/operator_summary.json` remains the only normal apply authority.
- The projection counts only mapping-shaped fallback and legacy-policy rows and
  preserves the specified surface names and first-attention behavior.
- `git diff --check` completed without whitespace errors.
- The pre-existing edit to `.superpowers/sdd/progress.md` was not changed.

# Task 6 Report: Keep the Guardrail Runner Focused on This Boundary

Status: DONE

## Files Changed

- `tests/test_check_contract_guardrails.py`
- `.superpowers/sdd/task-6-report.md`

`scripts/check_contract_guardrails.py` was not changed because the new runner-scope test passed against the existing `FOCUSED_CONTRACT_TESTS` list.

## Implementation

- Added `test_guardrail_runner_includes_source_contract_v2_boundary_tests`.
- The test asserts that `FOCUSED_CONTRACT_TESTS` includes the source-contract v2 boundary suite required by the task brief:
  - source claim family registry
  - contract spine sentinel, CLI, and docs tests
  - single apply authority and no-second-gate tests
  - semantic runtime negative boundaries
  - universal Wild no-block matrix
  - operator/docs active-path policy tests
  - claim-kind runtime, card behavior router, and mechanic support tests

## Evidence

Targeted runner coverage test:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py::test_guardrail_runner_includes_source_contract_v2_boundary_tests
```

Result:

```text
.                                                                        [100%]
1 passed in 0.07s
```

Full runner test file:

```powershell
python -m pytest -q tests/test_check_contract_guardrails.py
```

Result:

```text
....                                                                     [100%]
4 passed in 0.53s
```

## Concerns

- None for Task 6.
- Pre-existing unrelated working-tree change remains untouched: `.superpowers/sdd/task-1-report.md`.

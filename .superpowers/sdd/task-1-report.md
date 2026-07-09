# Task 1 Report: Add Config Usefulness Helper

## Summary

Implemented `build_config_usefulness(...)` as a pure helper in `src/hsconfig/config_usefulness.py` and added focused tests in `tests/test_config_usefulness.py`.

The helper stays read-only, does not touch `operator_summary.py` or `package_builder.py`, and keeps richness classification non-blocking for valid packages.

## TDD Evidence

### RED

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py -q
```

Result:

```text
ERROR collecting tests/test_config_usefulness.py
ModuleNotFoundError: No module named 'hsconfig.config_usefulness'
```

### GREEN

Command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py -q
```

Result:

```text
4 passed in 0.08s
```

## Changed Files

- `src/hsconfig/config_usefulness.py`
- `tests/test_config_usefulness.py`

## Tests

- `python -m pytest tests/test_config_usefulness.py -q`

## Self-Review

- The helper returns the required statuses: `guide_aligned`, `usable_with_targeted_gaps`, `load_safe_but_thin`, and `invalid_package`.
- `technical_status != VALID_PACKAGE` exits early with a non-blocking invalid-package payload and leaves runtime permission impact at `none`.
- The helper is defensive around missing or partial report dictionaries and keeps the normal operator gate untouched.
- I kept the card-ID surface thin when no meaningful runtime rows exist, which matches the visible test contract and preserves the "richness is not a hard blocker" rule.

## Review Fix

Fixed the card-ID usefulness classification so `_cardid_surface(...)` now returns `report_only` when there are no meaningful runtime rows but `report_only_supported > 0` in the readiness summary.

Added a focused regression test covering the report-only-only case and updated the sparse-package expectation to match the new contract.

Verification:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_config_usefulness.py -q
```

Result: `5 passed in 0.19s`

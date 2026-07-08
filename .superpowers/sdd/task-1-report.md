# Task 1 Report

## Status
DONE

## Changed Files
- `src/hsconfig/runtime_apply.py`
- `tests/test_runtime_apply.py`
- `.superpowers/sdd/task-1-report.md` (report artifact, not included in the Task 1 code commit)

## Commit Hashes
- `d9c48f566c7f2fde9391014b891173a3dc71087e` - `fix: gate direct runtime apply writes`

## Red Test Command and Output Summary
Command:

```powershell
python -m pytest tests\test_runtime_apply.py::test_apply_package_blocks_direct_write_without_operator_summary tests\test_runtime_apply.py::test_apply_package_rejects_forged_allowed_gate_without_operator_summary_path tests\test_runtime_apply.py::test_apply_package_direct_source_informed_requires_explicit_flag -q
```

Result before implementation:

```text
FFF [100%]
3 failed in 3.00s
```

Expected failure reason confirmed:
- `test_apply_package_blocks_direct_write_without_operator_summary` failed with `Failed: DID NOT RAISE ValueError`.
- `test_apply_package_rejects_forged_allowed_gate_without_operator_summary_path` failed with `Failed: DID NOT RAISE ValueError`.
- `test_apply_package_direct_source_informed_requires_explicit_flag` failed with `Failed: DID NOT RAISE ValueError`.

This matched the brief: direct `apply_package()` calls still wrote without resolving the operator gate and accepted a forged allowed gate dictionary.

## Green Test Command and Output Summary
Focused new-test rerun:

```powershell
python -m pytest tests\test_runtime_apply.py::test_apply_package_blocks_direct_write_without_operator_summary tests\test_runtime_apply.py::test_apply_package_rejects_forged_allowed_gate_without_operator_summary_path tests\test_runtime_apply.py::test_apply_package_direct_source_informed_requires_explicit_flag -q
```

Result:

```text
... [100%]
3 passed in 0.57s
```

Focused suite from the brief:

```powershell
python -m pytest tests\test_runtime_apply.py tests\test_runtime_apply_receipts.py tests\test_apply_gate.py -q
```

Result:

```text
.......................................................... [100%]
58 passed in 4.90s
```

Additional check:

```powershell
git diff --check -- src\hsconfig\runtime_apply.py tests\test_runtime_apply.py
```

Result: exit code `0`. Git printed CRLF normalization warnings for the two edited tracked files, but no whitespace errors.

## Self-Review Notes
- `apply_package()` now resolves an allowed apply gate before fake receipt generation, fake receipt verification, source validation, or runtime writes.
- Direct calls without `reports/operator_summary.json` now fail closed before mutating runtime files.
- Source-informed direct apply now requires `allow_source_informed=True`, matching the CLI gate behavior.
- Forged direct `apply_gate` dictionaries are rejected unless they are allowed and point at this package's `reports/operator_summary.json`.
- Generated fake receipts and final runtime apply receipts now persist the resolved gate.
- Existing direct-runtime tests that used hand-built packages were updated only enough to pass through the new gate and continue testing their original behavior.
- The Task 1 code commit includes only `src/hsconfig/runtime_apply.py` and `tests/test_runtime_apply.py`, per the brief's commit command.

## Concerns
- None.

## Review Fix Report

### Status
Resolved. Runtime writes now require the fresh `evaluate_apply_gate()` result; any caller-supplied `apply_gate` must exactly match that fresh evaluation before mutation.

### Changes
- Added `test_apply_package_rejects_forged_allowed_gate_with_matching_operator_summary_path`.
- Updated `_resolve_allowed_apply_gate()` to always derive the write gate with `evaluate_apply_gate(package, allow_source_informed=...)`.
- Rejected supplied gate dictionaries when they differ from the fresh evaluation, including forged allowed gates with matching `operator_summary_path`.
- Updated runtime apply tests so non-forgery cases use a real `evaluate_apply_gate()` result instead of fabricated allowed gates.
- Forwarded the CLI `--allow-source-informed` flag into `apply_package()` so CLI source-informed applies still satisfy the hardened direct API requirement.

### Red Test
```powershell
python -m pytest tests\test_runtime_apply.py::test_apply_package_rejects_forged_allowed_gate_with_matching_operator_summary_path -q
```

Result before implementation:

```text
FAILED tests/test_runtime_apply.py::test_apply_package_rejects_forged_allowed_gate_with_matching_operator_summary_path
Failed: DID NOT RAISE ValueError
```

### Green Tests
```powershell
python -m pytest tests\test_runtime_apply.py::test_apply_package_rejects_forged_allowed_gate_with_matching_operator_summary_path tests\test_runtime_apply.py::test_apply_package_blocks_direct_write_without_operator_summary tests\test_runtime_apply.py::test_apply_package_direct_source_informed_requires_explicit_flag -q
```

Result:

```text
3 passed in 0.73s
```

```powershell
python -m pytest tests\test_runtime_apply.py tests\test_runtime_apply_receipts.py tests\test_apply_gate.py -q
```

Result:

```text
59 passed in 5.93s
```

### Concerns
- None.

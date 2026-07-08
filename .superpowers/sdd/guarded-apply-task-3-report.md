# Task 3 Report: CLI Fake Apply And Receipt-Bound Apply

## Status

Complete.

## Scope

Implemented Task 3 in the requested branch:

- `src/hsconfig/cli_parser.py`
- `src/hsconfig/commands/apply.py`
- `tests/test_runtime_apply.py`

No changes were made to `src/hsconfig/runtime_apply.py`.
No docs or skill text were edited.

## TDD Evidence

Added the two brief-specified CLI tests first:

- `test_apply_cli_fake_mode_does_not_write_runtime`
- `test_apply_cli_from_fake_receipt_applies_matching_package`

Initial RED command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py::test_apply_cli_fake_mode_does_not_write_runtime tests/test_runtime_apply.py::test_apply_cli_from_fake_receipt_applies_matching_package -q
```

Expected RED result observed:

- `2 failed`
- Both failed with argparse `SystemExit: 2`
- Failure reason: `unrecognized arguments: --fake`

Added one extra RED regression test for the Task 2 review integration requirement:

- `test_apply_cli_normal_apply_persists_actual_apply_gate_in_fake_receipt`

Initial RED command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py::test_apply_cli_normal_apply_persists_actual_apply_gate_in_fake_receipt -q
```

Expected RED result observed:

- `1 failed`
- Failure reason: persisted fake receipt had `{"status": "not_checked"}` instead of the actual CLI `apply_gate`.

## Implementation

Extended `hsconfig apply` parser with:

- `--fake`
- `--from-fake-receipt`

Wired `apply_payload` so that:

- `hsconfig apply --fake --package <package> --runtime-root <runtime> --json` validates the package, evaluates the operator gate, calls `plan_apply_package(..., apply_gate=apply_gate)`, writes `reports/runtime_apply_fake_receipt.json`, and does not mutate runtime files.
- `hsconfig apply --from-fake-receipt <receipt> --package <package> --runtime-root <runtime> --json` reads the supplied receipt with `read_json`, passes it to `apply_package`, and relies on the existing receipt verification before runtime mutation.
- Normal `hsconfig apply --package <package> --runtime-root <runtime> --json` remains autonomous and now passes the actual `apply_gate` into `apply_package`, so the internally generated fake receipt persists the real gate instead of `{"status": "not_checked"}`.

## Verification

Focused GREEN command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py::test_apply_cli_fake_mode_does_not_write_runtime tests/test_runtime_apply.py::test_apply_cli_from_fake_receipt_applies_matching_package tests/test_runtime_apply.py::test_apply_cli_normal_apply_persists_actual_apply_gate_in_fake_receipt -q
```

Result:

- `3 passed in 0.74s`

Requested task test command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py tests/test_cli.py -q
```

Result:

- `47 passed in 19.50s`

## Concerns

None.

## Follow-up Fix: Fake Apply CLI Ambiguity

Task 3 minor ambiguity fixed:

- `hsconfig apply --fake` and `hsconfig apply --from-fake-receipt <path>` are now mutually exclusive at argparse parse time.
- No apply execution semantics were changed.

Added regression test:

- `tests/test_cli.py::test_apply_rejects_fake_and_from_fake_receipt_together`

TDD evidence:

- RED focused command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_cli.py::test_apply_rejects_fake_and_from_fake_receipt_together -q
```

- RED result: `1 failed`; failure reason was `Failed: DID NOT RAISE SystemExit`, proving both options were previously accepted and dispatched.

- GREEN focused command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_cli.py::test_apply_rejects_fake_and_from_fake_receipt_together -q
```

- GREEN result: `1 passed in 0.89s`.

Requested verification command:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/test_runtime_apply.py tests/test_cli.py -q
```

Result:

- `48 passed in 18.95s`

Concerns:

- None.

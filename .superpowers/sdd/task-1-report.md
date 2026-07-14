# Task 1 Report: Guard Report-Only Mechanics Against Runtime Block Hints

Status: DONE

## What Changed

- Added `test_report_only_modern_mechanics_ignore_explicit_runtime_block_hints` to `tests/test_card_behavior_router.py`.
- The test covers `imbue`, `forge`, and `excavate` mechanic-usage claims that supply an explicit `runtime_block`.
- The test proves these report-only mechanics:
  - emit no `card_rows`;
  - remain suppressed with `lowering_policy == "report_only"`;
  - keep the documented `<mechanic>_has_no_documented_runtime_block` reason;
  - do not copy `runtime_block` into suppressed diagnostic rows.

## TDD Evidence

### RED Step / Focused Test

Command:

```powershell
python -m pytest -q tests/test_card_behavior_router.py::test_report_only_modern_mechanics_ignore_explicit_runtime_block_hints
```

Result: passed immediately, so this task remained characterization coverage and no production fallback edit was made.

Output summary:

```text
.                                                                        [100%]
1 passed in 0.12s
```

### Full Router Test File

Command:

```powershell
python -m pytest -q tests/test_card_behavior_router.py
```

Result: passed.

Output summary:

```text
....................................                                     [100%]
36 passed in 0.11s
```

### Git Status Before Report Update

Command:

```powershell
git status --short --branch
```

Output summary:

```text
## codex/hsconfig-contract-spine-guard-wave...origin/codex/hsconfig-contract-spine-guard-wave
 M tests/test_card_behavior_router.py
```

## Production Fallback Decision

- The new focused regression passed immediately.
- Per the task brief, no production change was made to:
  - `src/hsconfig/card_behavior_surface_router.py`
  - `src/hsconfig/mechanic_support.py`

## Files Changed

- `tests/test_card_behavior_router.py`
- `.superpowers/sdd/task-1-report.md`

## Self-Review

- Scope stayed within the requested write scope.
- No runtime evidence, generated runtime package, operator path, or unrelated docs were changed.
- The test uses the real `route_card_behavior_claims` API and no mocks.
- The report-only boundary remains before any explicit runtime-block lowering behavior.

## Concerns

- None.

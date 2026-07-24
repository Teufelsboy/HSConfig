# Task 1 Important Fix Report

Scope: Source Readiness Preview important review finding.

## Review Finding

`SOURCE_BACKED_STRONG` plus non-empty `default_only_runtime_surfaces` was being reported as clean `source_backed_strong_ready` with no action required.

## RED

Added `test_preview_keeps_strong_default_only_surface_out_of_clean_ready_lane` in `tests/test_source_readiness_preview.py`.

Command:

```powershell
pytest tests/test_source_readiness_preview.py::test_preview_keeps_strong_default_only_surface_out_of_clean_ready_lane -q
```

Observed failure:

```text
assert preview["source_backed_strong_ready"] is False
E       assert True is False
```

Root cause: `src/hsconfig/source_readiness_preview.py` treated `semantic_status == "SOURCE_BACKED_STRONG"` as sufficient for clean `source_backed_strong_ready`, before accounting for `default_only_runtime_surfaces` or missing source action state.

## Fix

- Normalized `default_only_runtime_surfaces` before readiness calculation.
- Split raw strong signal from clean readiness.
- Kept `semantic_status` as `SOURCE_BACKED_STRONG` when reported by the operator summary.
- Set `source_backed_strong_ready` only when raw strong is present, default-only surfaces are empty, and `first_missing_source_action == "none"`.
- Added `default_only_runtime_surface_no_block` readiness lane for non-empty default-only runtime surfaces.
- Defaulted next source action for default-only runtime surfaces to `replace_default_only_runtime_surface_with_source_or_policy_claim` when no explicit action exists.
- Pinned `runtime_apply_authority` to `reports/operator_summary.json`.

## GREEN

Command:

```powershell
pytest tests/test_source_readiness_preview.py -q
```

Result:

```text
6 passed
```

## Boundaries

Changed only:

- `src/hsconfig/source_readiness_preview.py`
- `tests/test_source_readiness_preview.py`
- `.superpowers/sdd/task-1-important-fix-report.md`

No HSTuner work, runtime logs/replays, runtime writes, apply gates, or secondary apply authority were introduced.

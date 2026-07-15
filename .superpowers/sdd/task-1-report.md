# Task 1 Report: Source Bundle Artifact

## Status

`DONE_WITH_CONCERNS`

Commit: `79b76ab639c9081dcbfa6a4af76ee9d830c115f0` (`feat: write source bundle artifact`)

## Implemented

- Added `src/hsconfig/source_bundle.py` with `build_source_bundle(...)`.
  - Produces schema version 1 with deck identity, copied source records and claims,
    copied explainability card coverage, default-only surfaces, and promotion metadata.
  - Determines the first missing source action without changing package, apply, or
    runtime behavior.
  - Normalizes existing internal router action names to the Task-1 public diagnostic
    action contract only. This affects `source_bundle.json` explainability and does
    not contribute apply authority.
- Updated `src/hsconfig/commands/configure.py` to read the completed package
  reports, write `04_package/reports/source_bundle.json`, and expose the result as
  `source_bundle_path` in `configure_summary.json`.
- Added the unit schema test in `tests/test_source_bundle.py`.
- Added an online-source configure integration test in
  `tests/test_configure_online_source.py` and consolidated the existing online
  fixture setup into the shared helper used by both tests.

## Safety Boundaries Verified

- `operator_summary.json` remains the normal apply authority. Configure only reads
  it to construct the diagnostic bundle; it is not modified.
- `source_bundle.json` is written after package preparation and before validation.
  It is not passed to `apply_payload`, and it cannot alter runtime writes.
- The online-source test fixture's Darkbishop row (`SW_448`) remains a
  `hero_power_transform`, reports `next_source_action: "none"`, and is backed by
  `SW_448.json`; no Mulligan claim or opening-hand behavior was introduced.
- No decoded deck is blocked or made load-unsafe by this change. Existing configure
  source tests remain green and still assert `load_safe_apply`.
- Policy/default rows do not acquire new strong-promotion authority; the new bundle
  copies existing operator/explainability diagnostics only.

## TDD Evidence

### Red: required source-bundle schema test

Command:

```powershell
python -m pytest tests/test_source_bundle.py::test_source_bundle_exposes_source_claim_runtime_chain -q
```

Output:

```text
ERROR collecting tests/test_source_bundle.py
ModuleNotFoundError: No module named 'hsconfig.source_bundle'
1 error in 0.26s
```

### Green: source-bundle unit test

Command:

```powershell
python -m pytest tests/test_source_bundle.py -q
```

Output:

```text
1 passed in 0.10s
```

### Red: configure integration contract

Command:

```powershell
python -m pytest tests/test_configure_online_source.py::test_configure_writes_source_bundle_for_online_source -q
```

Output before public diagnostic normalization:

```text
AssertionError: assert 'add_runtime_lowerable_claim_or_router_support' in {
  'add_explicit_mulligan_source',
  'map_claim_kind_or_keep_report_only',
  'none',
  'replace_default_only_runtime_surface_with_source_or_policy_claim'
}
1 failed in 5.41s
```

The current fixture's internal report action came from already-emitted Mulligan
claims. The source-bundle projection now maps that internal action to the task's
public `add_explicit_mulligan_source` action while retaining the original report
unchanged.

### Green: focused Task-1 regression suite

Command:

```powershell
python -m pytest tests/test_source_bundle.py tests/test_configure_online_source.py tests/test_configure_auto_source.py -q
```

Final output:

```text
9 passed in 1.91s
```

### Additional checks

```powershell
git diff --check
```

Output: no whitespace errors.

## Concern

I started `python -m pytest -q` twice after the runner returned early while both
full-suite processes continued in the background. Both reached 16% progress but
did not finish after several minutes of sustained CPU use, so I terminated the
redundant processes to leave no active test runners. The required focused Task-1
suite passed; the full repository suite has not been completed in this task.

# Task 1 Report: Contract Spine Sentinel Core

## Result

Implemented the read-only contract spine sentinel core in
`src/hsconfig/contract_spine_sentinel.py` and added the required coverage in
`tests/test_contract_spine_sentinel.py`.

The sentinel consumes the supported atomic claim kinds, source-contract policy,
and source-contract conformance snapshot. It reports schema version `1`, clean
or drift-detected status, diagnostic-only operator impact, non-blocking apply
behavior, structured checks, and structured problems.

## TDD Evidence

1. Added the five sentinel tests before the implementation.
2. Ran the specified test command while the implementation was absent.
3. The test collection failed with the expected:
   `ModuleNotFoundError: No module named 'hsconfig.contract_spine_sentinel'`.
4. Added the minimal implementation.
5. Re-ran the specified command: `5 passed`.

## Verification

Targeted sentinel tests:

```text
5 passed in 0.09s
```

Focused regression tests for source-contract conformance and apply boundaries:

```text
29 passed in 0.16s
```

`git diff --check` completed without whitespace errors.

## Boundary Checks

- The sentinel is diagnostic-only and sets `apply_blocking` to `False`.
- It does not consume or alter `reports/operator_summary.json`, the normal
  runtime apply authority.
- It flags diagnostic-only consumers if they appear in active apply paths.
- It checks that conformance and contract-spine rows do not carry forbidden
  apply-authority fields.
- It preserves the Darkbishop boundary: `hero_power_transform` remains a
  `cardid` surface, while start-of-game effects remain rejected as opening-hand
  mulligan keeps without explicit hand-required evidence.
- No runtime evidence, new dependency, or unrelated source change was added.

## Commit

The implementation, tests, and this report are committed with:

```text
test: add contract spine sentinel core
```

# Task 4 Report: Source Freshness Provenance Normalizer

## Scope

Implemented Task 4 only in the authorized HSConfig files. The change projects
Task 3 freshness diagnostics through the research-result contract sentinel and
contract preflight. It remains diagnostic-only; `reports/operator_summary.json`
remains the only normal apply authority.

## TDD Evidence

1. Added `test_sentinel_counts_missing_freshness_without_apply_blocking`.
2. Added `test_contract_preflight_exposes_research_freshness_missing_count`.
3. RED command:

   ```powershell
   python -m pytest tests/test_research_result_contract_sentinel.py::test_sentinel_counts_missing_freshness_without_apply_blocking tests/test_contract_preflight.py::test_contract_preflight_exposes_research_freshness_missing_count -q
   ```

   Result: `2 failed`. Each failure was the expected absent field:
   `summary.freshness_missing_count` and
   `research_context.latest_research_result_contract_freshness_missing_count`.

4. GREEN command: same targeted command.

   Result: `2 passed in 3.71s`.

5. Required full target command:

   ```powershell
   python -m pytest tests/test_research_result_contract_sentinel.py tests/test_contract_preflight.py -q
   ```

   Result: `28 passed in 7.47s`.

## Changed Files

- `src/hsconfig/research_result_contract_sentinel.py`
  - Adds per-row `freshness_status`, `current_or_evergreen`, and
    `current_or_evergreen_reason` from strict validation.
  - Adds summary `freshness_missing_count` and `current_or_evergreen_count`.
- `src/hsconfig/contract_preflight.py`
  - Projects freshness-missing count into `ResearchContextPreflight`.
  - Returns zero for not-found, incomplete, and sentinel-exception fallbacks.
- `src/hsconfig/commands/contract_preflight.py`
  - Mirrors the zero fallback in the unavailable research-context payload.
- `tests/test_research_result_contract_sentinel.py`
  - Covers missing freshness reporting and updates the exact summary contract.
- `tests/test_contract_preflight.py`
  - Covers the preflight research-context projection.
- `.superpowers/sdd/task-4-report.md`
  - Records Task 4 implementation and verification evidence.

## Self-Review

- `source_status_apply_blocking` remains `False` in the sentinel, preflight
  payload, and unavailable fallback; freshness gaps are not apply authority.
- `reports/operator_summary.json` remains the normal runtime apply authority.
- No runtime apply/write, HSTuner, logs, online research, dependencies, or
  runtime surfaces were added or changed.
- No Darkbishop Benedictus or Mulligan behavior was touched.
- `git diff --check` completed with exit code 0 before commit.

## Commit

- Message: `feat: report research provenance gaps`
- Scope: the six Task 4 authorized files listed above.

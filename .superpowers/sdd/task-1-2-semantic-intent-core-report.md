# HSConfig Semantic Intent Coverage Diagnostic Tasks 1 and 2

## Result

Implemented the diagnostic-only `semantic_intent_coverage` check in the existing config-quality report.

The check rolls up existing card behavior, trace completeness, and mechanic runtime discipline facts. It also reads optional warning-only semantic metadata from `reports/semantic_enrichment_report.json`. It does not add runtime surfaces, apply gates, duplicate entries in `problems`, runtime writes, HSTuner behavior, replay parsing, or generated package changes.

## RED Evidence

Added the Task 1 assertions and the optional warning-only visibility test to `tests/test_config_quality_contract.py`.

Command:

```text
python -m pytest tests\test_config_quality_contract.py -q
```

Before the Task 2 implementation, the focused suite reported:

```text
5 failed, 15 passed
```

The failures were the expected missing `semantic_intent_coverage` key (`KeyError`) in the clean package, missing trace, report-only mechanic, semantic default, and warning-only semantic tests.

## GREEN Evidence

After implementation, the same focused command reported:

```text
20 passed in 0.41s
```

Additional checks:

```text
python -m py_compile src\hsconfig\config_quality_contract.py
```

Result: passed.

```text
git diff --check
```

Result: passed. Git emitted only the repository's existing LF-to-CRLF working-copy warnings.

## Files Changed

- `src/hsconfig/config_quality_contract.py`
  - Reads and normalizes the optional semantic enrichment report.
  - Adds the `semantic_intent_coverage` derived check after the existing base checks.
  - Summarizes missing trace, missing semantic score, semantic defaults, report-only runtime emission, and warning-only mechanics.
  - Keeps `authority` as `diagnostic_only`, `apply_blocking` as `False`, and `runtime_write_performed` as `False`.
- `tests/test_config_quality_contract.py`
  - Adds the clean report contract assertion.
  - Adds diagnostic assertions for missing trace, semantic defaults, and report-only mechanic emission.
  - Adds warning-only semantic visibility coverage.
- `.superpowers/sdd/task-1-2-semantic-intent-core-report.md`
  - This report.

## Concerns

No implementation concerns identified. The unrelated pre-existing modification to `.superpowers/sdd/progress.md` was preserved and is excluded from the commit.

# Task 3: Operator Surface Report

## Result

Implemented Semantic Intent Coverage Diagnostic Task 3. The existing
`checks.semantic_intent_coverage` diagnostic is now surfaced in both operator
outputs without changing apply authority or blocking behavior.

## Changes

- `src/hsconfig/commands/configure.py`
  - Extended `_compact_config_quality_summary` to include
    `semantic_intent_status` when the check is present.
  - Includes `semantic_intent_first_attention` when the diagnostic provides a
    value.
  - Preserved the existing config-quality failure fallback, including its
    `config_quality_summary_failed` problem check only.
- `src/hsconfig/contract_doctor.py`
  - Added Semantic Intent status and first-attention lines to the Config
    Quality Markdown section.
  - Uses `unknown` for a missing status and `none` for a missing first
    attention value.
- `tests/test_configure_cli.py`
  - Added coverage for the compact summary projection.
- `tests/test_contract_doctor.py`
  - Added coverage for both Semantic Intent Markdown lines.

## Tests Run

```text
python -m pytest tests\test_configure_cli.py tests\test_contract_doctor.py -q
26 passed in 7.82s
```

Additional self-review check:

```text
git diff --check
clean
```

## Files Changed

- `src/hsconfig/commands/configure.py`
- `src/hsconfig/contract_doctor.py`
- `tests/test_configure_cli.py`
- `tests/test_contract_doctor.py`
- `.superpowers/sdd/task-3-operator-surface-report.md`

## Concerns

No material concerns identified within the requested scope. The full test
suite was not run; verification was limited to the focused configure and
contract-doctor tests specified by the task brief.

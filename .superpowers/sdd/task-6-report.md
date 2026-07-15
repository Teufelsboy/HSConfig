# Task 6 Report: Explainability and First Missing Source Action

Status: DONE

## Files Changed

- `src/hsconfig/source_to_runtime_explainability.py`
- `tests/test_source_to_runtime_explainability.py`
- `.superpowers/sdd/task-6-report.md`

`src/hsconfig/source_claim_gap_report.py` and `tests/test_source_claim_gap_report.py` were exercised by the focused test run but did not need code changes.

## Implementation

- Added a policy-backed autonomous mulligan regression that covers compact `audit={claim_rows: [...]}` input plus `runtime_files`.
- Kept the existing positional `source_contract_audit_report` input path working.
- Added per-card `source_lane`, `first_missing_source_action`, and `runtime_lowering_status`.
- Mirrored the same three fields into `operator_attention` so the operator-facing row names the source lane, the first missing source action, and the runtime lowering state.
- Preserved legacy `best_source_lane`, `next_source_action`, and `closure` fields.

## Red Evidence

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py -q
```

Result before implementation:

```text
1 failed, 22 passed in 0.33s
```

Failure:

```text
TypeError: build_source_to_runtime_explainability_report() got an unexpected keyword argument 'audit'
```

## Green Evidence

Focused task tests:

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py -q
```

Result:

```text
23 passed in 0.34s
```

Directly relevant operator/closure tests:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_source_contract_closure_wave.py -q
```

Result:

```text
91 passed in 14.79s
```

## Concerns

- The red test initially failed at the new compact interface boundary rather than at field lookup. That still proves the requested compact source-policy explainability path was absent before implementation.
- Pre-existing unrelated working-tree edits remain untouched in docs and skill files outside this task scope.

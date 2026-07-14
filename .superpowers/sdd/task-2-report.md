# Task 2 Report

## Status

DONE

## Task

Add a compact active source-contract spine reference while keeping it diagnostic-only and outside the normal operator command path.

## Changed Files

- `docs/operator/source-contract-spine.md`: new diagnostic source-contract spine reference covering normal runtime surfaces, all supported claim kinds, false-lowering boundaries, and the single apply authority.
- `docs/operator/README.md`: added a late diagnostic pointer to `docs/operator/source-contract-spine.md` without adding it to the first normal-path section.
- `docs/operator/guide-research-policy.md`: added the source-to-runtime decision rule.
- `tests/test_operator_docs_contract_policy.py`: added Task 2 docs-policy tests for the new reference and README placement.
- `.superpowers/sdd/task-2-report.md`: implementation evidence for this worker task.

## RED Evidence

Command:

```powershell
python -m pytest -q tests/test_operator_docs_contract_policy.py::test_source_contract_spine_reference_is_active_but_not_an_apply_gate tests/test_operator_docs_contract_policy.py::test_operator_readme_links_source_contract_spine_without_normal_path_drift
```

Result:

```text
2 failed in 0.20s
```

Expected failures:

- `test_source_contract_spine_reference_is_active_but_not_an_apply_gate` failed with `FileNotFoundError` for `docs/operator/source-contract-spine.md`.
- `test_operator_readme_links_source_contract_spine_without_normal_path_drift` failed because `docs/operator/README.md` did not yet contain `docs/operator/source-contract-spine.md`.

## GREEN Evidence

Command:

```powershell
python -m pytest -q tests/test_operator_docs_contract_policy.py tests/test_docs_active_path.py
```

Result:

```text
42 passed in 0.17s
```

Additional check:

```powershell
git diff --check -- docs/operator/source-contract-spine.md docs/operator/README.md docs/operator/guide-research-policy.md tests/test_operator_docs_contract_policy.py
```

Result: exit code 0; only existing CRLF normalization warnings were printed.

## Scope Notes

- Did not modify `.superpowers/sdd/task-1-report.md`.
- Did not add HSTuner, replay parsing, winrate validation, post-game tuning, candidate promotion, runtime-evidence analysis, new runtime surfaces, or a second apply gate.
- Preserved `reports/operator_summary.json` as the only normal apply authority.
- Preserved the Darkbishop Benedictus boundary: effect semantics can stay encoded, but start-of-game hero-power effects are not opening-hand mulligan keeps without explicit opening-hand evidence.

## Concerns

- The working tree had a pre-existing modification to `.superpowers/sdd/task-1-report.md`; it was not touched or staged by this task.

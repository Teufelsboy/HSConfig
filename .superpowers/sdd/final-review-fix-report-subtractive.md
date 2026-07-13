# Final Review Fix Report - Subtractive Contract Polish

## Files changed

- `src/hsconfig/role_tokens.py`
- `src/hsconfig/source_document_model.py`
- `src/hsconfig/research_contract.py`
- `src/hsconfig/gameplan_contract.py`
- `src/hsconfig/output_ownership_manifest.py`
- `src/hsconfig/contract_spine_sentinel.py`
- `docs/operator/source-builder-workflow.md`
- `docs/superpowers/plans/2026-07-13-hsconfig-subtractive-contract-polish.md`
- `tests/test_claim_kind_runtime_contract.py`
- `tests/test_surface_authority_split.py`
- `tests/test_archetype_source_fixtures.py`
- `tests/test_subtractive_contract_polish.py`
- `tests/test_contract_spine_sentinel.py`
- `tests/test_docs_active_path.py`

## Tests run and results

- Red regression subset before implementation: 9 failed as expected.
- Focused review suite: `$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_surface_authority_split.py tests/test_archetype_source_fixtures.py tests/test_subtractive_contract_polish.py tests/test_report_ownership.py tests/test_contract_spine_sentinel.py tests/test_docs_active_path.py -q` -> 148 passed.
- Post-review regression subset for unknown research reports: `$env:PYTHONPATH='src'; python -m pytest tests/test_subtractive_contract_polish.py::test_output_ownership_manifest_marks_unknown_report_unclassified tests/test_contract_spine_sentinel.py::test_contract_spine_sentinel_flags_injected_unknown_research_report -q` -> 2 failed before implementation, then 2 passed.
- Post-review focused review suite: `$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py tests/test_surface_authority_split.py tests/test_archetype_source_fixtures.py tests/test_subtractive_contract_polish.py tests/test_report_ownership.py tests/test_contract_spine_sentinel.py tests/test_docs_active_path.py -q` -> 149 passed.
- Sentinel: `$env:PYTHONPATH='src'; python -m hsconfig contract-spine-sentinel --json` -> `status=clean`, `apply_blocking=false`, `problems=[]`.
- Working diff whitespace: `git diff --check` -> passed, with Git CRLF warnings only.
- Working-tree branch whitespace: `git diff --check edbb86f3a5c9f02af28af684b7fef475f091a5e2` -> passed, with Git CRLF warnings only.

## Any remaining risks

- Full repository test suite must be rerun by the main agent after the post-review fix commit.
- The exact committed branch-range whitespace check must be re-run after the commit because `git diff --check edbb86f3a5c9f02af28af684b7fef475f091a5e2 HEAD` only evaluates committed changes.

## Commit hash

- Final commit hash is reported in the task response after commit creation; this report is part of that commit and cannot contain its own final SHA before the commit exists.

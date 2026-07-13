## Final-review fix: embedded string role hints

Status: fixed and committed in this changeset.

Changed files:
- `src/hsconfig/source_document_model.py`
- `tests/test_claim_kind_runtime_contract.py`
- `.superpowers/sdd/contract-guard-final-review-fix-report.md`

Commit id: same commit as this report; exact final hash is reported in the task response because a commit cannot contain its own final hash.

RED command/output summary:
- Command: `$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py::test_claim_embedded_string_roles_and_semantic_families_suppress_mulligan_keep_without_external_card_roles tests/test_claim_kind_runtime_contract.py::test_claim_embedded_string_semantic_and_mechanic_families_suppress_mulligan_keep_without_external_card_roles -q`
- Output summary: `FF [100%]`; both tests failed because `SurfaceGateDecision` returned `allowed=True` with reason `allowed`; `2 failed in 0.38s`.

GREEN command/output summary:
- Command: `$env:PYTHONPATH='src'; python -m pytest tests/test_claim_kind_runtime_contract.py -q`
- Output summary: `................................ [100%]`; `32 passed in 0.24s`.

Self-review notes:
- Added regression coverage for string-valued embedded role hints with empty `card_roles`.
- Kept the fix local to `_roles_for_card()` by adding `_role_tokens()`.
- `_role_tokens()` treats strings as single role tokens, iterates list/tuple/set/frozenset containers, strips/lowercases string tokens, and ignores None, empty strings, and non-string scalar values.
- Re-ran the two new tests after the fix and saw `2 passed in 0.25s`.
- Did not touch replay parsing, winrate logic, HSTuner orchestration, runtime apply gates, Presume/Concede normal paths, or post-game candidate promotion.

Concerns:
- No code concerns from the targeted run. The exact containing commit hash cannot be embedded in this committed report without changing the hash; the final task response records it.
